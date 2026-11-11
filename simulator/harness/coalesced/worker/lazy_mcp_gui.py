"""Discover the original MCP tool schemas without taking the world's action lease."""
import argparse
import json
from pathlib import Path
import sys
import threading
import base64
import hashlib
import io
from PIL import Image
from mcp.types import ImageContent

p = argparse.ArgumentParser()
p.add_argument('--config',type=Path,required=True)
p.add_argument('--sdk',type=Path,required=True)
p.add_argument('--image-ledger', type=Path)
p.add_argument('--compact-depth', action='store_true')
a = p.parse_args()
for name in tuple(sys.modules):
    if name == 'vic_sdk' or name.startswith('vic_sdk.'):
        del sys.modules[name]
sys.path.insert(0,str(a.sdk))
from vic_sdk.embodied_codex_mcp import NativeStructuredTools, make_server
from public_read_identity import install as install_read_identity
NativeStructuredTools, make_server = install_read_identity(NativeStructuredTools, make_server)
if a.compact_depth:
    from public_depth import install
    NativeStructuredTools, make_server = install(NativeStructuredTools, make_server)

def bounded_image(block):
    if not a.image_ledger or block.type != 'image':
        return block
    raw = base64.b64decode(block.data, validate=True)
    encoded = raw
    mime = block.mimeType
    mode = 'original'
    with Image.open(io.BytesIO(raw)) as image:
        size = list(image.size)
        if len(block.data) > 200*1024:
            buffer = io.BytesIO()
            image.save(buffer, format='WEBP', lossless=True, method=4)
            encoded, mime, mode = buffer.getvalue(), 'image/webp', 'lossless'
        if len(encoded)>150*1024:
            for quality in (96,94,92,90):
                buffer=io.BytesIO()
                image.save(buffer,format='WEBP',quality=quality,method=4)
                encoded,mime,mode=buffer.getvalue(),'image/webp','WebP quality '+str(quality)
                if len(encoded)<=150*1024:
                    break
        if len(encoded) > 150*1024:
            for quality in (93,88,82,75,65,55,45):
                buffer = io.BytesIO()
                image.convert('RGB').save(buffer, format='JPEG', quality=quality, optimize=True)
                encoded, mime, mode = buffer.getvalue(), 'image/jpeg', 'JPEG quality '+str(quality)
                if len(encoded)<=150*1024:
                    break
        if len(encoded)>150*1024:
            raise ValueError('Cannot fit full GUI image within native inline budget')
    digest = hashlib.sha256
    record=dict(original_sha256=digest(raw).hexdigest(), input_bytes=len(raw), encoded_bytes=len(encoded),
                encoded_sha256=digest(encoded).hexdigest(),size=size, encoding=mode, mime=mime)
    with a.image_ledger.open('a') as f:
        f.write(json.dumps(record)+'\n')
    return ImageContent(type='image', mimeType=mime, data=base64.b64encode(encoded).decode())


class LazyGUI:
    def __init__(self):
        self.backend = None
        self.config = json.loads(a.config.read_text())
        self.lock = threading.Lock()

    def __getattr__(self,name):
        if name not in ('information','action_batch','history','terminal'):
            raise AttributeError(name)
        def call(*args, **kwargs):
            with self.lock:
                if self.backend is None:
                    self.backend = NativeStructuredTools(json.loads(a.config.read_text()))
                result = getattr(self.backend, name)(*args, **kwargs)
                if a.image_ledger:
                    result.content = [bounded_image(b) for b in result.content]
                return result
        return call

    def close(self):
        with self.lock:
            if self.backend is not None:
                self.backend.close()

backend = LazyGUI()
try:
    make_server(backend).run(transport='stdio')
finally:
    backend.close()
