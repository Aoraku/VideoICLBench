"""Frozen payload equivalence and an atomic two-contender directory gate."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
import ast,base64,gzip,hashlib,json,subprocess,sys
import pytest

PREPARE=Path(__file__).parents[2]/'verification/task-design-revision-20261102/prepare_engineering_compact_transport.py'


def metadata(tmp_path,corrupt=False):
    target=tmp_path/'target';reference=tmp_path/'reference';target.mkdir();reference.mkdir()
    payload={'videoicl_isaaclab/a.py':'a=1\n','videoicl_isaaclab/b.py':'b=2\n'}
    hashes={k:hashlib.sha256(v.encode()).hexdigest()for k,v in payload.items()}
    (target/'source-hashes.private.json').write_text(json.dumps(dict(hashes,**({'videoicl_isaaclab/a.py':'0'*64}if corrupt else{}))))
    (reference/'source-hashes.private.json').write_text(json.dumps({'videoicl_isaaclab/a.py':hashes['videoicl_isaaclab/a.py']}))
    blob=base64.b64encode(gzip.compress(json.dumps(payload).encode())).decode()
    source="import pathlib,base64,gzip,json,subprocess\nroot=pathlib.Path('/unused')\np=root/'engineering/execution-design-v3-20261102-test-new';p.mkdir(exist_ok=False)\nr=p/'runtime'\nfor name,txt in json.loads(gzip.decompress(base64.b64decode("+repr(blob)+"))).items():(r/name).write_text(txt)\nenv={'CONTROL':'positive','SEED':'4201'}\ncmd=['python3','probe.py','--rooms','1']\nsubprocess.Popen(cmd,env=env)\n"
    (target/'launch.py').write_text(source);(reference/'launch.py').write_text("p=root/'engineering/execution-design-v3-20261102-test-old'\n")
    return target,reference,source


def test_compact_transport_preserves_payload_argv_env_and_pre_spawn_atomic_gate(tmp_path):
    target,reference,source=metadata(tmp_path)
    subprocess.run([sys.executable,str(PREPARE),str(target),str(reference)],check=True,capture_output=True,text=True)
    compact=(target/'launch-compact-transport.py').read_text();ast.parse(compact)
    proof=json.loads((target/'compact-transport-equivalence.private.json').read_text())
    assert proof['reused_source_files']==1 and proof['embedded_source_files']==1
    assert proof['frozen_source_bytes_changed']is False and proof['original_launch_file_changed']is False
    assert proof['original_launch_sha256']==hashlib.sha256(source.encode()).hexdigest()
    assert proof['compact_launch_sha256']==hashlib.sha256(compact.encode()).hexdigest()
    assert (target/'launch.py').read_text()==source
    for prefix in('env=','cmd=','subprocess.Popen'):
        assert [l for l in source.splitlines()if l.startswith(prefix)]==[l for l in compact.splitlines()if l.startswith(prefix)]
    assert compact.index('p.mkdir(exist_ok=False)')<compact.index('subprocess.Popen')


def test_bad_frozen_payload_metadata_is_rejected_before_transport_generation(tmp_path):
    target,reference,source=metadata(tmp_path,corrupt=True)
    r=subprocess.run([sys.executable,str(PREPARE),str(target),str(reference)],capture_output=True,text=True)
    assert r.returncode and not(target/'launch-compact-transport.py').exists()
    assert (target/'launch.py').read_text()==source


def test_two_contenders_only_one_atomic_unique_root_no_child_created(tmp_path):
    root=tmp_path/'single-native-world';ready=Barrier(2)
    def contender():
        ready.wait()
        try:root.mkdir(exist_ok=False);return True
        except FileExistsError:return False
    with ThreadPoolExecutor(max_workers=2)as pool:result=list(pool.map(lambda _:contender(),range(2)))
    assert sorted(result)==[False,True]and root.is_dir()and list(root.iterdir())==[]
