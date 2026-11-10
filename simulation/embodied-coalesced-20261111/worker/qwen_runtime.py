"""Native Qwen/Claude tool waits: an accepted physical action is not an idle failure."""

def configure_tool_wait(env):
    # CLI 2.1.292 has a separate MCP idle timer. MCP_TOOL_TIMEOUT does not
    # disable that 30-minute timer. A shared native pool may legitimately wait
    # longer; aborting only the CLI call leaves the physical operation running.
    # Keep the native call attached until it returns or the owner reports failure.
    env['CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT'] = '0'
    return {
        'native_mcp_idle_timeout_ms': 0,
        'native_mcp_idle_timeout_disabled': True,
        'accepted_operations_cancelled': False,
        'effort_changed': False,
        'reason': 'Preserve the accepted native operation while shared-pool tools wait',
    }


def configure_provider_wait(env):
    """Keep a long upstream response attached; preserve effort and native history.

    CLI 2.1.292 predates API_TIMEOUT_MS=0 support, so use a positive 24h
    response-header allowance and separately disable the three streaming timers.
    The owner still supplies the authoritative terminal/recovery policy.
    """
    policy = {
        'API_TIMEOUT_MS': '86400000',
        'CLAUDE_ENABLE_STREAM_WATCHDOG': '0',
        'CLAUDE_ENABLE_BYTE_WATCHDOG': '0',
        'API_FORCE_IDLE_TIMEOUT': '0',
    }
    env.update(policy)
    return {'native_provider_wait_environment': policy,
            'native_header_timeout_ms': 86400000,
            'native_stream_watchdogs_disabled': True,
            'native_body_idle_timeout_disabled': True,
            'effort_changed': False, 'history_reconstructed': False,
            'inflight_api_cancelled': False}
