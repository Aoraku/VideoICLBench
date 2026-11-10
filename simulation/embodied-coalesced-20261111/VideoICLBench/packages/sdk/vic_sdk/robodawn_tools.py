"""Synchronous Responses bridge to the existing, episode-local GUI MCP tools.

This adapter does not execute a second action implementation. FastMCP keeps its
argument validation, frame guards, ProgramGuiSession, and idempotency receipts.
There is deliberately no timeout, retry, stdio server, shell, or reset facility.
Images retain their original encoded bytes and are returned separately from text.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
import hashlib
import inspect
import json
import re
import threading
from typing import Any


GUI_TOOL_NAMES = frozenset({
    "observe", "depth_points", "act", "program", "done", "giveup",
    "demo_info", "demo_frame", "demo_frames",
})


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class ToolResult:
    name: str
    text_blocks: list[dict[str, Any]]
    images: list[dict[str, Any]]
    raw: Any
    is_error: bool = False
    structured_content: dict[str, Any] | None = None
    image_sources: list[dict[str, Any]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(block["text"] for block in self.text_blocks)

    def response_output(self, call_id: str) -> dict[str, Any]:
        """Text-only function output; caller places ``images`` in live context.

        Responses has no MCP isError flag. Preserve it explicitly in the error
        output rather than letting an error message appear to be a success.
        ``raw`` remains available for the local audit; it is never serialized as
        text, because it can contain image base64.
        """
        output = self.text
        if self.is_error:
            output = json.dumps({"isError": True, "text": output}, ensure_ascii=False)
        return {"type": "function_call_output", "call_id": call_id, "output": output}


def convert_result(name: str, result: Any) -> ToolResult:
    """Normalize public FastMCP 1.x return forms without flattening image data."""
    raw = _plain(result)
    structured = None
    is_error = False
    if isinstance(raw, dict) and "content" in raw:
        content = raw["content"]
        structured = raw.get("structuredContent")
        is_error = bool(raw.get("isError", False))
    elif isinstance(result, tuple) and len(result) == 2:
        content, structured = _plain(result[0]), _plain(result[1])
    elif isinstance(raw, list):
        content = raw
    elif isinstance(raw, dict):
        structured = raw
        content = []
    else:
        raise TypeError("Unsupported FastMCP result shape")
    if not isinstance(content, list):
        raise TypeError("FastMCP result content must be a sequence")
    text_blocks, images = [], []
    for block in content:
        if not isinstance(block, dict):
            raise TypeError("Unsupported FastMCP content block")
        kind = block.get("type")
        if kind == "text" and isinstance(block.get("text"), str):
            text_blocks.append({"type": "input_text", "text": block["text"]})
        elif kind == "image":
            mime, data = block.get("mimeType"), block.get("data")
            if not isinstance(mime, str) or not mime.startswith("image/") or not isinstance(data, str):
                raise ValueError("Invalid MCP image content")
            images.append({"type": "input_image", "image_url": f"data:{mime};base64,{data}", "detail": "high"})
        else:
            # Do not stringify arbitrary binary resources/audio into a prompt.
            raise TypeError(f"Unsupported MCP content type: {kind!r}")
    if not text_blocks and structured is not None:
        text_blocks.append({"type": "input_text", "text": json.dumps(structured, ensure_ascii=False)})
    return ToolResult(name, text_blocks, images, raw, is_error, structured)


class GUIBridge:
    """Own one async MCP loop plus the existing thread-owned GUI browser.

    A supplied ``server`` is dependency injection for tests and is never started
    as a network/stdio service. Calls are serialized, including shutdown. Never
    cancel a call to obtain a timeout: a GUI commit may already be accepted.
    """

    def __init__(self, config: dict[str, Any], server: Any = None):
        self.config = dict(config)
        self._server = server
        self._browser = None
        self._tools = None
        self._closed = False
        self._lock = threading.RLock()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="vic-robodawn-mcp", daemon=True)
        self._thread.start()
        try:
            self._submit(self._initialize())
        except BaseException:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join()
            self._loop.close()
            self._closed = True
            raise

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coroutine):
        if threading.current_thread() is self._thread:
            coroutine.close()
            raise RuntimeError("Synchronous GUIBridge cannot be called from its owner loop")
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result()

    async def _initialize(self):
        if self._server is None:
            from .embodied_gui_mcp import ThreadOwnedBrowser, make_server
            self._browser = ThreadOwnedBrowser(self.config)
            try:
                self._server = make_server(self._browser)
            except BaseException:
                self._browser.close()
                self._browser = None
                raise

    def list_tools(self) -> list[dict[str, Any]]:
        with self._lock:
            self._require_open()
            if self._tools is None:
                listed = self._submit(self._server.list_tools())
                tools = []
                seen = set()
                for item in listed:
                    tool = _plain(item)
                    name = tool.get("name")
                    if name not in GUI_TOOL_NAMES:
                        continue
                    if name in seen:
                        raise ValueError("Duplicate registered GUI tool")
                    seen.add(name)
                    tools.append({"type": "function", "name": name,
                                  "description": tool.get("description", ""),
                                  "parameters": tool["inputSchema"], "strict": False})
                self._tools = tools
            # Callers may add a note tool; do not let them mutate this registry.
            return json.loads(json.dumps(self._tools))

    def _require_open(self):
        if self._closed:
            raise RuntimeError("GUIBridge is closed")

    def _with_image_sources(self, result: ToolResult, arguments: dict[str, Any]) -> ToolResult:
        """Classify media using tool identity or the program's exact output lists.

        Never infer image provenance from resolution, visual appearance, or a
        model-written label. Unknown provenance is explicit for the context
        manager to reject, rather than silently turning a GUI view into a demo.
        Session arrays are read only after this serialized call has completed.
        """
        kinds = ["unknown"] * len(result.images)
        basis = "unavailable"
        timestamps = [None] * len(result.images)
        if result.name in {"observe", "act", "done", "giveup"}:
            kinds, basis = ["gui"] * len(result.images), "registered_gui_tool"
        elif result.name in {"demo_frame", "demo_frames"}:
            kinds, basis = ["demo"] * len(result.images), "registered_demo_tool"
            requested = arguments.get("seconds")
            if result.name == "demo_frame":
                if len(result.images) == 1:
                    timestamps = [requested]
            elif isinstance(requested, list) and len(requested) == len(result.images):
                timestamps = sorted(requested)
        elif result.name == "program" and result.images:
            session = getattr(self._server, "_episode_program_session", None)
            if session is not None:
                gui = list(session.gui_images)
                demo = list(session.demo_images)
                expected = convert_result("program", gui + demo).images
                if expected == result.images:
                    kinds = ["gui"] * len(gui) + ["demo"] * len(demo)
                    basis = "program_session_exact_gui_then_demo_image_lists"
        sources = [{"kind": kind, "basis": basis, "image_index": index,
                    "encoded_image_sha256": hashlib.sha256(image["image_url"].encode()).hexdigest(),
                    "demo_seconds": timestamp if kind == "demo" else None}
                   for index, (image, kind, timestamp) in enumerate(zip(result.images, kinds, timestamps))]
        return replace(result, image_sources=sources)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        with self._lock:
            self._require_open()
            if name not in {tool["name"] for tool in self.list_tools()}:
                raise ValueError(f"Tool is not registered for this episode: {name}")
            if not isinstance(arguments, dict):
                raise TypeError("Tool arguments must be a JSON object")
            try:
                raw = self._submit(self._server.call_tool(name, arguments))
            except Exception as exc:
                # Match MCP's error envelope. Never retry or call another tool.
                raw = {"isError": True, "content": [{"type": "text", "text": str(exc)}],
                       "bridge_error_type": type(exc).__name__}
                return convert_result(name, raw)
            try:
                return self._with_image_sources(convert_result(name, raw), arguments)
            except Exception as exc:
                # The call has completed. Keep its exact returned result for
                # reconciliation even if a new/unsupported media type cannot
                # be represented in this bridge. Do not execute it again.
                return ToolResult(name, [{"type": "input_text", "text": str(exc)}],
                                  [], _plain(raw), True)

    def public_action_inputs(self, action: dict[str, Any]) -> list[dict[str, Any]]:
        """Compile a model-selected public pair into visible GUI inputs.

        This is a deterministic GUI macro for decision-turn mode. It never
        calls the controller action endpoint, reads simulator objects, or
        exposes DOM/selectors to the model. The original ``act`` still owns
        frame guards, acknowledgement, the one-Commit limit and screenshots.
        """
        with self._lock:
            self._require_open()
            if self._browser is None:
                raise ValueError('Public GUI action macros require the real thread-owned browser')

            def compile_inputs():
                page = self._browser.browser.page
                size = page.viewport_size

                def click(selector):
                    item = page.locator(selector)
                    if item.count() != 1 or not item.is_visible() or not item.is_enabled():
                        raise ValueError('Public action control is unavailable: ' + selector)
                    box = item.bounding_box()
                    if not box or not size:
                        raise ValueError('Public action control has no visible geometry')
                    x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
                    if not (0 <= x < size['width'] and 0 <= y < size['height']):
                        raise ValueError('Public action control is outside the current GUI viewport')
                    return dict(kind='click', x=x, y=y)

                inputs = []
                for side in ('left', 'right'):
                    token = action[side]
                    if not isinstance(token, str) or not re.fullmatch(r'[A-Z_]+', token):
                        raise ValueError('Expected a public GUI action token')
                    inputs.append(click('#' + side + '-actions button[data-token="' + token + '"]'))
                for selector, value in (('#step-mm', action['step_mm']), ('#rotation-deg', action['rotation_deg'])):
                    inputs.extend([click(selector), dict(kind='key', key='ControlOrMeta+A'),
                                   dict(kind='text', text=str(value))])
                inputs.append(click('#commit'))
                return inputs

            return self._browser.executor.submit(compile_inputs).result()

    def public_queue_inputs(self, operation: str, *, batch_id=None):
        """Compile visible queue controls only; execution remains original GUI act."""
        with self._lock:
            self._require_open()
            if self._browser is None:
                raise ValueError('Batch controls require the real thread-owned public browser')
            selectors = {'clear':'#queue-clear','add':'#queue-add','commit':'#commit','id':'#batch-id'}
            if operation not in selectors:
                raise ValueError('Unknown public queue control')
            if operation == 'id' and (not isinstance(batch_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',batch_id)):
                raise ValueError('Stable bounded public batch ID required')
            def compile_inputs():
                page = self._browser.browser.page
                item = page.locator(selectors[operation])
                if item.count()!=1 or not item.is_visible() or not item.is_enabled():
                    raise ValueError('Public batch control unavailable: '+selectors[operation])
                box=item.bounding_box();size=page.viewport_size
                if not box or not size:
                    raise ValueError('Public batch control has no visible geometry')
                x,y=box['x']+box['width']/2,box['y']+box['height']/2
                if not 0<=x<size['width'] or not 0<=y<size['height']:
                    raise ValueError('Public batch control is outside the current GUI viewport')
                inputs=[dict(kind='click',x=x,y=y)]
                if operation=='id':
                    inputs.extend([dict(kind='key',key='ControlOrMeta+A'),dict(kind='text',text=batch_id)])
                return inputs
            return self._browser.executor.submit(compile_inputs).result()

    def public_action_count(self) -> int | None:
        """Read the same visible budget counter shown in the GUI."""
        with self._lock:
            self._require_open()
            if self._browser is None:
                return None
            return self._browser.executor.submit(self._browser.browser._visible_action_count).result()

    async def _shutdown(self):
        session = getattr(self._server, "_episode_program_session", None)
        try:
            if session is not None:
                result = session.close()
                if inspect.isawaitable(result):
                    await result
        finally:
            if self._browser is not None:
                self._browser.close()

    def close(self):
        with self._lock:
            if self._closed:
                return
            try:
                self._submit(self._shutdown())
            finally:
                self._closed = True
                self._loop.call_soon_threadsafe(self._loop.stop)
                self._thread.join()
                self._loop.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
