"""Place ZCode's already-returned GUI pixels where GLM's Messages adapter reads them."""
import base64
import hashlib
import json
from collections import Counter

IMAGE_TOOLS = {'mcp__vic__observe','mcp__vic__action_batch','mcp__vic__demo_frames',
               'mcp__vic__history','mcp__vic__depth_points','mcp__vic__done','mcp__vic__giveup'}


def fingerprint(block):
    src = block.get('source') or {}
    if src.get('type') != 'base64' or src.get('media_type') not in {'image/jpeg','image/png','image/webp'}:
        raise ValueError('Unsupported GUI image transport')
    return hashlib.sha256(base64.b64decode(src['data'], validate=True)).hexdigest()


def promote(data, ledger):
    """Move bytes within the same user message only; verify tool origin and encoded digest."""
    emitted = None
    calls = {}
    relocated = []
    for msg in data.get('messages', []):
        blocks = msg.get('content')
        if not isinstance(blocks, list):
            continue
        if msg['role'] == 'assistant':
            for b in blocks:
                if b.get('type') == 'tool_use':
                    calls[b['id']] = b.get('name')
            continue
        if msg['role'] != 'user':
            continue
        existing = Counter(fingerprint(b) for b in blocks if b.get('type')=='image')
        extra = []
        for result in blocks:
            if result.get('type') != 'tool_result' or not isinstance(result.get('content'), list):
                continue
            parts = result['content']
            outgoing = []
            cid = result.get('tool_use_id')
            for part in parts:
                if part.get('type') != 'image':
                    outgoing.append(part)
                    continue
                if calls.get(cid) not in IMAGE_TOOLS:
                    raise ValueError('Missing public MCP tool-use owner for this frame')
                if emitted is None:
                    emitted = {row['encoded_sha256'] for line in ledger.read_bytes().splitlines(keepends=True)
                               if line.endswith(b'\n') and (row:=json.loads(line)).get('encoded_sha256')}
                digest = fingerprint(part)
                if digest not in emitted:
                    raise ValueError('Image absent from room MCP delivery ledger')
                # Keep original result order (including multi-frame video) explicit.
                number = 1 + len([x for x in relocated if x['tool_use_id']==cid])
                label = f'Image {number} of tool result {cid}'
                outgoing.append({'type':'text','text':label+' follows in this user message.'})
                if existing[digest]:
                    existing[digest] -= 1
                else:
                    extra.extend(({'type':'text','text':label}, part))
                relocated.append(dict(tool_use_id=cid,tool=calls[cid],index=number,sha256=digest))
            result['content'] = outgoing
        if extra:
            # All tool_result blocks must precede other content. Place associated frames
            # before any subsequent user instruction to preserve its natural read order.
            index = max(i for i,b in enumerate(blocks) if b.get('type')=='tool_result')+1
            blocks[index:index] = extra
    return relocated
