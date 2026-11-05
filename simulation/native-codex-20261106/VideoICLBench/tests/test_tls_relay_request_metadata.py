"""No provider calls. Pure metadata tests plus optional loopback TLS fixture."""
import hashlib
import http.client
import json

import pytest

from vic_sdk.tls_relay import safe_request_metadata, ResponseOutcomeObserver
from tests.test_tls_relay import upstream, relay


def test_public_counts_hashes_do_not_export_any_content_or_credentials():
    body = json.dumps(dict(prompt_cache_key='SESSION_PRIVATE', instructions='PRIVATE_SYSTEM',
        tools=[dict(type='function', name='PRIVATE_TOOL', parameters={})], input=[
        dict(role='user', content=[dict(type='input_text', text='PRIVATE_TASK'),
                                  dict(type='input_image', image_url='data:image/png;base64,PRIVATE_IMAGE')]),
        dict(type='function_call_output', output=[dict(type='input_text', text='PRIVATE_RETURN'),
            dict(type='input_image', image_url='data:image/png;base64,PRIVATE_IMAGE')])])).encode()
    headers = {'Authorization':'Bearer PRIVATE_AUTH', 'session-id':'SESSION_PRIVATE',
               'session_id':'SESSION_PRIVATE', 'Cookie':'PRIVATE_COOKIE'}
    original_headers = dict(headers)
    result = safe_request_metadata(body, headers)
    encoded = json.dumps(result)
    for secret in ('PRIVATE_', 'SESSION_PRIVATE', 'Bearer', 'data:image', 'Authorization', 'Cookie'):
        assert secret not in encoded
    assert headers == original_headers
    assert result['body_sha256'] == hashlib.sha256(body).hexdigest()
    assert result['input_count'] == 2 and result['image_count'] == 2
    assert result['items'][0]['text_utf8_bytes'] == [len('PRIVATE_TASK')]
    assert result['items'][1]['text_utf8_bytes'] == [len('PRIVATE_RETURN')]
    assert len(set(result['cache_header_sha256'].values())) == 1
    assert result['prompt_cache_key_sha256'] == next(iter(result['cache_header_sha256'].values()))


def test_absent_cache_key_is_not_added_or_claimed_valid():
    body = b'{"input":"task"}'
    got = safe_request_metadata(body, {})
    assert got['prompt_cache_key_present'] is False
    assert got['prompt_cache_key_sha256'] is None
    assert got['cache_header_sha256'] == {}
    assert got['input_string_utf8_bytes'] == 4


@pytest.mark.parametrize('body', [b'not json', b'[]', b'\x1f\x8bgzip', b'\xff'])
def test_unknown_encoding_or_nonobject_metadata_does_not_raise(body):
    result = safe_request_metadata(body, {})
    assert result['parse_valid'] is False
    assert result['body_bytes'] == len(body)


def test_weird_typed_role_cannot_raise_or_export_opaque_string():
    got = safe_request_metadata(b'{"input":[{"role":{},"type":[],"content":"PRIVATE"}]}', {})
    assert got['items'][0]['role'] is None
    assert got['items'][0]['type'] == 'other'
    assert 'PRIVATE' not in json.dumps(got)


def test_history_prefix_hashes_show_unchanged_native_items():
    prefix = [dict(role='developer', content='constant'), dict(role='user', content='initial')]
    first = safe_request_metadata(json.dumps(dict(input=prefix)).encode(), {})
    second = safe_request_metadata(json.dumps(dict(input=prefix+[dict(role='assistant', content='new')])).encode(), {})
    assert [x['sha256'] for x in first['items']] == [x['sha256'] for x in second['items'][:2]]
    assert first['body_sha256'] != second['body_sha256']


@pytest.mark.parametrize('enabled', [False, True])
def test_actual_tls_forward_preserves_original_body_header_and_default_optout(tmp_path, upstream, enabled):
    body = b'{"prompt_cache_key":"NATIVE_SESSION","input":[{"role":"user","content":"PRIVATE_CONTENT"}]}'
    with relay(tmp_path, upstream, request_metadata=enabled) as (details, server):
        client = http.client.HTTPConnection('127.0.0.1', server.server_port)
        client.request('POST', '/v1/responses', body,
            {'Authorization':'Bearer PRIVATE_AUTH','session-id':'NATIVE_SESSION'})
        response = client.getresponse()
        assert response.status == 200
        assert response.read() == upstream[3]
        client.close()
        assert details['request_metadata_enabled'] is enabled
    assert upstream[2][0]['body'] == body
    assert upstream[2][0]['authorization'] == 'Bearer PRIVATE_AUTH'
    raw = (tmp_path/'relay/transport.private.jsonl').read_text()
    record = json.loads(raw)
    assert ('request_metadata' in record) is enabled
    assert 'PRIVATE_CONTENT' not in raw and 'PRIVATE_AUTH' not in raw and 'NATIVE_SESSION' not in raw
    if enabled: assert record['request_metadata']['body_sha256'] == hashlib.sha256(body).hexdigest()


def test_metadata_inspector_failure_never_cancels_or_replays_request(tmp_path, upstream, monkeypatch):
    def fail(*_): raise ValueError('PRIVATE_EXCEPTION_MUST_NOT_BE_LOGGED')
    monkeypatch.setattr('vic_sdk.tls_relay.safe_request_metadata', fail)
    with relay(tmp_path, upstream, request_metadata=True) as (_, server):
        client = http.client.HTTPConnection('127.0.0.1', server.server_port)
        client.request('POST', '/v1/responses', b'{"input":"original"}')
        response = client.getresponse()
        assert response.status == 200 and response.read() == upstream[3]
        client.close()
    assert len(upstream[2]) == 1 and upstream[2][0]['body'] == b'{"input":"original"}'
    raw = (tmp_path/'relay/transport.private.jsonl').read_text()
    assert 'PRIVATE_EXCEPTION' not in raw
    assert json.loads(raw)['request_metadata']['inspection_failed'] is True


def test_terminal_usage_is_numeric_request_anchored_duplicate_completed_is_not_added():
    observer=ResponseOutcomeObserver(200,'text/event-stream',usage_metadata=True)
    event=dict(type='response.completed', response=dict(id='PRIVATE_PROVIDER_ID',status='completed',
        usage=dict(input_tokens=416000,input_tokens_details=dict(cached_tokens=407000,
            cache_write_tokens=100,cache_write_tokens_details=dict(ttl_30m_tokens=100,ttl_12h_tokens=0)),
            output_tokens=33,output_tokens_details=dict(reasoning_tokens=0),total_tokens=416033,
            opaque_private_field='DO_NOT_EXPORT')))
    data=('data: '+json.dumps(event)+'\n\n').encode()
    observer.feed(data+data)
    assert observer.finish()==('success',None)
    assert len(observer.provider_usage_records)==1 and observer.provider_usage_duplicate_events==1
    got=observer.provider_usage_records[0]
    assert got['input_tokens']==416000 and got['cached_input_tokens']==407000
    assert got['output_tokens']==33 and got['reasoning_output_tokens']==0
    assert got['cache_write_tokens']==100 and got['cache_write_ttl_12h_tokens']==0
    assert 'PRIVATE_PROVIDER_ID' not in json.dumps(got) and 'DO_NOT_EXPORT' not in json.dumps(got)


def test_conflicting_completed_usage_is_explicit_not_summed_or_silently_chosen():
    observer=ResponseOutcomeObserver(200,'text/event-stream',usage_metadata=True)
    def emit(n):
        observer.feed(('data: '+json.dumps(dict(type='response.completed',response=dict(id='same',
            status='completed',usage=dict(input_tokens=n,output_tokens=7))))+'\n\n').encode())
    emit(226960);emit(477372)
    assert observer.finish()==('success',None)
    assert observer.provider_usage_conflict is True
    assert len(observer.provider_usage_records)==2
    assert observer.provider_usage_records[0]['cached_input_tokens'] is None


def test_failed_response_usage_kept_if_provided_and_optout_never_collects():
    event=dict(type='response.failed',response=dict(id='failed',status='failed',usage=dict(input_tokens=100,
        output_tokens=1)))
    data=('data: '+json.dumps(event)+'\n\n').encode()
    enabled=ResponseOutcomeObserver(200,'text/event-stream',usage_metadata=True);enabled.feed(data)
    disabled=ResponseOutcomeObserver(200,'text/event-stream');disabled.feed(data)
    assert enabled.finish()[0]=='failure' and len(enabled.provider_usage_records)==1
    assert disabled.provider_usage_records==[]
