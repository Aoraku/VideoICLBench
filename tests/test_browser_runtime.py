from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from vic.runtime import BrowserRuntime


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['/apps/chat/run', '/native/chat/run/', '/native/product/blog/run'])
async def test_all_application_entries_resolve_worker(monkeypatch, path):
    monkeypatch.setenv('VIC_APPLICATION_BASE', 'http://applications:8771')
    monkeypatch.setattr('vic.runtime.socket.gethostbyname', lambda host: '172.18.0.3')
    page = SimpleNamespace(goto=AsyncMock())
    context = SimpleNamespace(new_page=AsyncMock(return_value=page), close=AsyncMock())
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
    chromium = SimpleNamespace(launch=AsyncMock(return_value=browser))
    runtime = BrowserRuntime()
    runtime.driver = SimpleNamespace(chromium=chromium)
    await runtime.ensure('run', 'http://application.localhost:8771' + path + '#secret')
    assert chromium.launch.call_args.kwargs['args'] == ['--host-resolver-rules=MAP application.localhost 172.18.0.3']
    await runtime.close_run('run')
    context.close.assert_awaited_once()
    browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_navigation_releases_owned_browser():
    page = SimpleNamespace(goto=AsyncMock(side_effect=RuntimeError('navigation failed')))
    context = SimpleNamespace(new_page=AsyncMock(return_value=page), close=AsyncMock())
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())
    runtime = BrowserRuntime()
    runtime.driver = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
    with pytest.raises(RuntimeError, match='navigation failed'):
        await runtime.ensure('run', 'http://127.0.0.1:8771/apps/chat/run')
    assert not runtime.sessions
    context.close.assert_awaited_once()
    browser.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('source,expected', [('Return', 'Enter'), ('ControlOrMeta+Left', 'ControlOrMeta+ArrowLeft'), ('ArrowDown', 'ArrowDown')])
async def test_common_keyboard_aliases(source, expected):
    import asyncio
    import time
    page = SimpleNamespace(keyboard=SimpleNamespace(press=AsyncMock()), wait_for_timeout=AsyncMock())
    session = {'action_lock': asyncio.Lock(), 'actions': {}, 'frame': 1, 'created': time.monotonic(), 'page': page}
    runtime = BrowserRuntime()
    runtime.ensure = AsyncMock(return_value=session)
    action = SimpleNamespace(action_id='one', frame=1, kind='key', key=source,
                             model_dump=lambda: {'action_id': 'one', 'kind': 'key', 'key': source})
    await runtime.act('run', 'http://local', action)
    page.keyboard.press.assert_awaited_once_with(expected)
