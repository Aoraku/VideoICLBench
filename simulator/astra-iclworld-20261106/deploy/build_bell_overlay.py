"""Regenerate E26C/I derived bell files from the original mechanism asset directory."""
import argparse
import hashlib
import json
import math
import re
import shutil
import tempfile
from pathlib import Path

FACTOR = 1.06
REL = Path('inference-generalization-v1/assets/g1/E26/bell_xy106')

def map_array(text,name,normal=False):
    count=0
    def sub(match):
        nonlocal count
        # Preserve unchanged sourceY point/extent spelling, not merely a rounded value.
        vectors=re.findall(r'\(([^()]+)\)',match.group(2));out=[]
        for raw in vectors:
            parts=[s.strip()for s in raw.split(',')];v=list(map(float,parts));assert len(v)==3 and all(map(math.isfinite,v))
            if normal:
                v=[v[0]/FACTOR,v[1],v[2]/FACTOR];length=math.sqrt(sum(x*x for x in v))
                if length:v=[x/length for x in v]
                out.append('('+', '.join(format(x,'.17g')for x in v)+')')
            else:out.append('('+format(v[0]*FACTOR,'.17g')+', '+parts[1]+', '+format(v[2]*FACTOR,'.17g')+')')
        count+=1
        return match.group(1)+'['+', '.join(out)+']'
    text=re.sub(r'('+re.escape(name)+r'\s*=\s*)(\[[^\n]+\])',sub,text)
    return text,count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mechanisms', type=Path, required=True, help='original VIC_MECHANISM_ASSETS')
    parser.add_argument('--output', type=Path, required=True, help='new overlay directory')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must be a fresh directory')
    records = json.loads(Path(__file__).with_name('runtime-sha256.json').read_text())
    records = {Path(k).relative_to(REL): v for k, v in records.items() if k.startswith(REL.as_posix() + '/')}
    assert len(records) == 9
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as tmp:
        root = Path(tmp) / 'overlay' / REL
        for rel, expected in sorted(records.items()):
            src = args.mechanisms / rel
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if rel.name == 'desk_bell_spring.usda':
                dst.write_text(src.read_text().replace('#usda 1.0', '#usda 1.0\n# Derived bell instance: worldXY1.06; original joints, sourceframes and worldZ retained.', 1))
            elif rel.suffix == '.usda':
                text = src.read_text()
                for field, count in [('point3f[] points', 2), ('float3[] extent', 2), ('normal3f[] normals', 1)]:
                    text, n = map_array(text, field, normal=field.startswith('normal3f'))
                    if n != count:
                        raise ValueError(f'Wrong source geometry: {rel}')
                dst.write_text(text)
            elif rel.name.endswith('.provenance.json'):
                mesh = rel.with_name(rel.name.replace('.provenance.json', '.usda'))
                data = dict(schema='videoicl-derived-source-bell-instance-v1',
                            original_conversion=json.loads(src.read_bytes()), original_source_modified=False,
                            new_scan_claimed=False, source_sha256=hashlib.sha256((args.mechanisms / mesh).read_bytes()).hexdigest(),
                            derived_sha256=records[mesh],
                            derivation='sourceX/Z baked1.06; sourceY/Z-worldheight retained; normals inverse-transpose; topology/materials unchanged')
                dst.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
            else:
                shutil.copyfile(src, dst)
            if hashlib.sha256(dst.read_bytes()).hexdigest() != expected:
                raise ValueError(f'Derived SHA256 mismatch: {rel}')
        (Path(tmp) / 'overlay').rename(args.output)


if __name__ == '__main__':
    main()
