"""No relay socket: actual child Python must ignore preloaded ambient SDKs."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT=Path(__file__).parents[1]


def contaminated_env(tmp_path):
    old=tmp_path/'vic_sdk';old.mkdir()
    (old/'__init__.py').write_text('AMBIENT_OLD=True\n')
    (old/'tls_relay.py').write_text("raise RuntimeError('ambient relay must never run')\n")
    (old/'native_agent.py').write_text("raise RuntimeError('ambient native_agent must never run')\n")
    (old/'embodied_agent.py').write_text("raise RuntimeError('ambient embodied_agent must never run')\n")
    (tmp_path/'sitecustomize.py').write_text("import vic_sdk\nimport sys,types\nm=types.ModuleType('vic_sdk.tls_relay');m.__file__='AMBIENT-OLD-RELAY';sys.modules[m.__name__]=m\n")
    return dict(os.environ,PYTHONPATH=str(tmp_path))


def test_relay_absolute_entry_help_loads_new_metadata_flag_despite_preloaded_old_sdk(tmp_path):
    env=contaminated_env(tmp_path)
    # Prove the fixture really loads an old parent AND an old child module.
    check=subprocess.run([sys.executable,'-c',"import vic_sdk,sys;print(vic_sdk.AMBIENT_OLD,sys.modules['vic_sdk.tls_relay'].__file__)"],
        capture_output=True,text=True,env=env,timeout=10)
    assert check.returncode==0 and 'True AMBIENT-OLD-RELAY' in check.stdout
    entry=ROOT/'packages/sdk/vic_sdk/tls_relay_entry.py'
    result=subprocess.run([sys.executable,str(entry),'--help'],capture_output=True,text=True,env=env,timeout=15)
    assert result.returncode==0,result.stderr
    assert '--request-metadata' in result.stdout and '--episode-timing-routes' in result.stdout
    assert 'ambient' not in result.stderr


@pytest.mark.parametrize('script', ['run_embodied_pool.py','serve_embodied_pool_room.py'])
def test_owned_pool_and_gui_entry_help_ignore_preloaded_sdk(tmp_path,script):
    env=contaminated_env(tmp_path)
    result=subprocess.run([sys.executable,str(ROOT/'scripts/harbor'/script),'--help'],
        capture_output=True,text=True,env=env,timeout=15)
    assert result.returncode==0,result.stderr
    assert '--max-actions' in result.stdout
    assert 'ambient' not in result.stderr


def test_pool_relay_command_uses_absolute_pinned_bootstrap_not_module_resolution():
    import ast
    source=(ROOT/'scripts/harbor/run_embodied_pool.py').read_text()
    tree=ast.parse(source)
    assignments=[node for node in ast.walk(tree) if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Name) and target.id=='relay_command' for target in node.targets)]
    assert len(assignments)==1
    command=ast.unparse(assignments[0].value)
    assert "ROOT / 'packages/sdk/vic_sdk/tls_relay_entry.py'" in command
    assert "'-m'" not in command


def test_library_import_of_pool_helper_does_not_replace_loaded_sdk_modules():
    import importlib.util
    import vic_sdk.embodied_environment.pool as original
    path=ROOT/'scripts/harbor/run_embodied_pool.py'
    spec=importlib.util.spec_from_file_location('pool_pinned_import_regression',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert sys.modules['vic_sdk.embodied_environment.pool'] is original


def test_relocated_frozen_sdk_relay_help_does_not_resolve_back_to_canonical(tmp_path):
    import shutil
    ambient=tmp_path/'ambient';ambient.mkdir();env=contaminated_env(ambient)
    frozen=tmp_path/'frozen/VideoICLBench/packages/sdk/vic_sdk'
    shutil.copytree(ROOT/'packages/sdk/vic_sdk',frozen,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    result=subprocess.run([sys.executable,str(frozen/'tls_relay_entry.py'),'--help'],
        capture_output=True,text=True,env=env,timeout=15)
    assert result.returncode==0,result.stderr
    assert '--request-metadata' in result.stdout
