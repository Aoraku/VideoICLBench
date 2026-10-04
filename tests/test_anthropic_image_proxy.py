import json

import httpx

from vic_sdk.anthropic_image_proxy import image_compat_proxy, lift_tool_images


def test_lift_is_lossless_idempotent_and_retains_tool_order():
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "bytes"}}
    payload = {"model": "test", "system": "unchanged", "stream": True,
               "messages": [{"role": "assistant", "content": [{"type": "tool_use", "id": "a"}]},
                            {"role": "user", "content": [
                                {"type": "tool_result", "tool_use_id": "a", "content": [image, {"type": "text", "text": "frame 7"}]},
                                {"type": "tool_result", "tool_use_id": "b", "content": [image]}]}]}
    before = json.dumps(payload)
    result, count = lift_tool_images(payload)
    blocks = result["messages"][1]["content"]
    assert count == 2 and [b["type"] for b in blocks] == ["tool_result", "tool_result", "image", "image"]
    assert blocks[0]["content"] == [{"type": "text", "text": "frame 7"}]
    assert blocks[1]["tool_use_id"] == "b" and blocks[1]["content"] == []
    assert blocks[2:] == [image, image]
    assert json.dumps(payload) == before
    assert lift_tool_images(result) == (result, 0)
    assert result["model"] == payload["model"] and result["system"] == payload["system"]
    assert result["messages"][0] == payload["messages"][0]


def test_proxy_preserves_stream_and_uses_fixed_authenticated_upstream(tmp_path, monkeypatch):
    requests = []
    data = b'data: {"type":"message_start"}\n\ndata: {"type":"message_stop"}\n\n'
    def handler(request):
        requests.append(request)
        assert request.url == 'https://example.test/v1/messages?beta=true'
        assert request.headers['authorization'] == 'Bearer upstream-secret'
        assert request.headers['anthropic-version'] == '2023-06-01'
        assert json.loads(request.content)['messages'][0]['content'][-1]['type'] == 'image'
        return httpx.Response(200, stream=httpx.ByteStream(data), headers={'content-type': 'text/event-stream'})
    real_client = httpx.Client
    monkeypatch.setattr('vic_sdk.anthropic_image_proxy.httpx.Client',
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    log = tmp_path / 'transport.jsonl'
    with image_compat_proxy('https://example.test/v1', 'upstream-secret', log) as (url, token), real_client() as caller:
        assert caller.post(url + '/v1/messages', json={}).status_code == 403
        assert caller.post(url + '/not-allowed', headers={'Authorization': 'Bearer ' + token}, json={}).status_code == 404
        r = caller.post(url + '/v1/messages?beta=true', headers={
            'Authorization': 'Bearer ' + token, 'anthropic-version': '2023-06-01'}, json={
            'messages': [{'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'a',
                'content': [{'type': 'image', 'source': {'type': 'base64', 'data': 'bytes'}}]}]}]})
        assert r.content == data and r.status_code == 200
    assert len(requests) == 1
    assert json.loads(log.read_text())['images_lifted'] == 1
    assert 'secret' not in log.read_text() and 'bytes' not in log.read_text()
