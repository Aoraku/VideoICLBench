"""Offline native CLI contract tests: no API, installed CLI or simulator needed."""
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'packages/sdk'))
from vic_sdk.native_cli_engines import dsh, zcode


class NativeDshZcodeContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.server = {'command': '/native/python', 'args': ['gui.py'], 'env': {'ONLY_GUI': '1'}}
        self.provider = {'base_url': 'http://localhost:9876/anthropic', 'api_key': 'offline-dummy',
                         'wire_api': 'anthropic-messages'}

    def configure(self, module, **options):
        return module.configure(self.root / module.__name__.split('.')[-1], self.root / 'workspace',
                                'flash-model', self.server, self.provider, options)

    def output(self, events):
        p = self.root / 'output.jsonl'
        p.write_text('\n'.join(json.dumps(x) for x in events) + '\n')
        return p

    def test_dsh_profile_is_native_messages_gui_only_and_private(self):
        receipt = self.configure(dsh, context_window=1050000, compact_tokens=945000)
        profile = self.root / 'dsh'
        rows = json.loads((profile / 'profiles/headless/cordis.patch.yml').read_text())
        disabled = {r['id'] for r in rows if r.get('disabled') is True}
        self.assertTrue({'tool-bash', 'tool-fs', 'tool-fs-search', 'tool-subagent',
                         'tool-web', 'mcp-resources', 'session-log-deepseek'} <= disabled)
        llm = next(r['config'] for r in rows if r.get('id') == 'llm-deepseek')
        self.assertNotIn('protocol', llm)
        self.assertEqual(llm['models'][0]['inputModalities'], ['text', 'image'])
        self.assertEqual(llm['baseURL'], self.provider['base_url'])
        self.assertNotIn('offline-dummy', json.dumps(receipt))
        for p in profile.rglob('*'):
            if p.is_file(): self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)

    def test_dsh_refuses_responses_and_unsafe_compaction_budget(self):
        with self.assertRaises(ValueError):
            dsh.configure(self.root, self.root, 'flash', self.server,
                          dict(self.provider, wire_api='responses'), {})
        with self.assertRaises(ValueError): self.configure(dsh, compact_tokens=1040000)
        with self.assertRaises(ValueError): self.configure(dsh, cli_version='unknown-build')

    def test_dsh_explicit_session_and_stdin(self):
        self.configure(dsh)
        cmd, env = dsh.command(self.root / 'dsh', self.root, 'flash', resume='exact-session')
        self.assertEqual(cmd[-3:], ['--session-id', 'exact-session', '-'])
        self.assertEqual(env['DSH_TELEMETRY_DISABLED'], '1')
        self.assertEqual(env['DEEPSEEK_API_KEY'], 'offline-dummy')
        self.assertNotIn('--model', cmd)

    def test_dsh_usage_sums_steps_and_keeps_missing_cache_unknown(self):
        p = self.output([{'type': 'session', 'sessionId': 's'},
            {'type': 'status', 'phase': 'step_end', 'usage': {'inputTokens': 8, 'outputTokens': 2}},
            {'type': 'status', 'phase': 'step_end', 'usage': {'inputTokens': 3, 'outputTokens': 1}},
            {'type': 'final', 'sessionId': 's', 'reason': {'kind': 'completed'}, 'text': 'answer'}])
        r = dsh.summarize(p, self.root)
        self.assertEqual(r['usage']['input_tokens'], 11)
        self.assertIsNone(r['usage']['cached_input_tokens'])
        self.assertFalse(r['is_error'])

    def test_dsh_missing_attempt_usage_invalidates_total_and_error_final(self):
        p = self.output([{'type': 'status', 'phase': 'step_end', 'usage': {'inputTokens': 8}},
            {'type': 'status', 'phase': 'step_end'},
            {'type': 'final', 'sessionId': 's', 'reason': {'kind': 'error'}, 'text': ''}])
        r = dsh.summarize(p, self.root)
        self.assertIsNone(r['usage']); self.assertTrue(r['is_error'])

    def test_dsh_rc5_final_uses_owned_last_turn_end_only(self):
        p = self.output([{'type': 'session', 'sessionId': 's'},
                         {'type': 'status', 'phase': 'turn_end', 'reason': {'kind': 'completed'}},
                         {'type': 'final', 'text': 'answer'}])
        self.assertFalse(dsh.summarize(p, self.root)['is_error'])
        p = self.output([{'type': 'session', 'sessionId': 's'},
                         {'type': 'status', 'phase': 'turn_end', 'reason': {'kind': 'completed'}},
                         {'type': 'status', 'phase': 'turn_start', 'turn': 2},
                         {'type': 'final', 'text': 'partial answer'}])
        self.assertTrue(dsh.summarize(p, self.root)['is_error'])

    def test_dsh_session_mismatch_and_truncated_stream_fail(self):
        p = self.output([{'type': 'session', 'sessionId': 'wrong'}])
        self.assertTrue(dsh.summarize(p, self.root, 'expected')['is_error'])

    def test_dsh_native_zstd_compact_usage_is_exact_session_and_current_turn(self):
        import zstandard
        native = self.root / 'sessions/workspace/session-exact/session.v4.jsonl.zstd'
        native.parent.mkdir(parents=True)
        events = []
        for turn, compact_id, tokens in [(1, 'old', 100), (2, 'current', 20)]:
            events += [{'type': 'compaction/start', 'data': {'turn': turn, 'compactionId': compact_id}},
                       {'type': 'compaction/summary', 'data': {'compactionId': compact_id,
                        'usage': {'inputTokens': tokens, 'outputTokens': 3}}},
                       {'type': 'compaction/end', 'data': {'turn': turn, 'compactionId': compact_id}}]
        native.write_bytes(zstandard.ZstdCompressor().compress(
            ('\n'.join(json.dumps(x) for x in events) + '\n').encode()))
        output = self.output([{'type': 'session', 'sessionId': 'session-exact'},
            {'type': 'status', 'phase': 'turn_start', 'turn': 2},
            {'type': 'status', 'phase': 'turn_end', 'reason': {'kind': 'completed'}},
            {'type': 'final', 'text': 'ok'}])
        r = dsh.summarize(output, self.root)
        self.assertFalse(r['is_error'])
        self.assertEqual(len(r['compaction_events']), 3)
        self.assertEqual(r['compaction_usage']['input_tokens'], 20)
        self.assertIsNone(r['compaction_usage']['cached_input_tokens'])

    def test_zcode_current_native_model_rule_and_compact_unknown(self):
        receipt = self.configure(zcode, context_window=1050000, compact_tokens=945000)
        home = self.root / 'zcode/home'
        p = json.loads((home / '.zcode/v2/provider_config.json').read_text())
        self.assertEqual(p['config']['defaultModelSelection']['modelId'], 'flash-model')
        self.assertEqual(p['config']['providerConfigRules']['providerRules'][0]['config']['api']['type'],
                         'anthropic-messages')
        self.assertEqual(receipt['context_window'], 1050000)
        self.assertIsNone(receipt['compact_tokens'])
        rule = p['config']['modelConfigRules']['providerModelRules'][0]
        self.assertEqual(rule['config']['properties']['contextWindow'], 1050000)
        self.assertTrue(rule['config']['properties']['inputFormat']['supportsImage'])
        self.assertNotIn('offline-dummy', json.dumps(receipt))
        runtime = json.loads((home / '.zcode/cli/config.json').read_text())
        self.assertTrue(runtime['features']['mcp']); self.assertFalse(runtime['features']['subagent'])
        self.assertEqual(list(runtime['mcp']['servers']), ['vic'])

    def test_zcode_js_binary_and_resume_are_native_args_after_carrier(self):
        self.configure(zcode)
        cmd, env = zcode.command(self.root / 'zcode', self.root, 'flash',
                                 binary='/official/dist/zcode.cjs', resume='s')
        self.assertEqual(cmd[3:5], ['node', '/official/dist/zcode.cjs'])
        self.assertEqual(cmd[-2:], ['--resume', 's'])
        self.assertNotIn('--model', cmd)
        self.assertEqual(env['HOME'], str((self.root / 'zcode/home').resolve()))

    def test_zcode_stdin_exec_preserves_unicode_newlines_and_no_shell(self):
        # Real local exec carrier, replacing the agent with a tiny argv recorder.
        recorder = self.root / 'record.py'
        recorder.write_text('import sys,json;print(json.dumps(sys.argv[1:],ensure_ascii=False))')
        prompt = '观察：第一行\n\n继续，保留末尾换行\n'
        r = subprocess.run([sys.executable, zcode.__file__, '--stdin-exec', sys.executable,
                            str(recorder), '--cwd', str(self.root)], input=prompt,
                           text=True, capture_output=True, check=True)
        args = json.loads(r.stdout)
        self.assertEqual(args[-2:], ['--prompt', prompt])

    def test_zcode_native_result_preserves_usage_and_unknown(self):
        p = self.output([{'type': 'result', 'sessionId': 's', 'response': 'done',
                         'usage': {'inputTokens': 17}, 'projection': {'contextWindow': 1000000}}])
        r = zcode.summarize(p, self.root)
        self.assertEqual(r['usage'], {'inputTokens': 17})
        self.assertEqual(r['native_projection']['contextWindow'], 1000000)
        self.assertTrue(r['model_response_observed']); self.assertFalse(r['is_error'])
        p = self.output([{'type': 'result', 'sessionId': 's', 'response': ''}])
        self.assertIsNone(zcode.summarize(p, self.root)['usage'])
        p = self.output([{'type': 'session.updated', 'payload': {'contextWindow': 1050000}},
                         {'type': 'result', 'response': 'ok', 'projection': {'contextWindow': 200000}}])
        r = zcode.summarize(p, self.root)
        self.assertEqual(r['native_model_context_window'], 1050000)
        self.assertEqual(r['native_projection']['contextWindow'], 200000)
        p = self.output([{'type': 'session.updated', 'payload':
                        {'trigger': 'auto', 'compactReason': 'context_limit', 'autoCompactThreshold': 1016000}},
                        {'type': 'result', 'response': 'ok'}])
        self.assertEqual(len(zcode.summarize(p, self.root)['compaction_events']), 1)

    def test_zcode_actual_mapped_events_preserve_tools_and_native_errors(self):
        p = self.output([
            {'type': 'tool.updated', 'sessionId': 's', 'payload':
             {'kind': 'scheduled', 'toolCallId': 'call-1', 'toolName': 'mcp__vic__program'}},
            {'type': 'tool.updated', 'sessionId': 's', 'payload':
             {'kind': 'started', 'toolCallId': 'call-1', 'toolName': 'mcp__vic__program'}},
            {'type': 'turn.failed', 'sessionId': 's', 'payload': {'message': 'provider error'}},
            {'type': 'result', 'sessionId': 's', 'response': ''}])
        r = zcode.summarize(p, self.root)
        self.assertEqual(len(r['tool_calls']), 1)
        self.assertTrue(r['is_error'])
        self.assertTrue(r['model_response_observed'])

    def test_zcode_invalid_stream_and_missing_result_fail(self):
        p = self.output([{'type': 'error', 'message': 'native failure'}])
        self.assertTrue(zcode.summarize(p, self.root)['is_error'])
        p.write_text('{truncated')
        self.assertTrue(zcode.summarize(p, self.root)['is_error'])


if __name__ == '__main__': unittest.main()
