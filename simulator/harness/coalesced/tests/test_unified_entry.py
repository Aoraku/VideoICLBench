"""Exercise public entry-to-worker configuration without a simulator or API."""
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pool_verified as pool
import bootstrap_verified_room as bootstrap
ENGINES=('codex','claude','qwen','dsh','zcode','kimi','gemini')
def parsed(engine,extras=()):
 return pool.build_parser().parse_args(['--native-python','/native/python','--gui-python',sys.executable,'--runtime-root','/runtime','--cases','/cases.json','--engine',engine,'--epoch','offline','--out','/out','--allow-unvalidated-environment',*extras])
@pytest.mark.parametrize('engine',ENGINES)
def test_all_engines_use_same_concurrent_pool_and_worker(engine):
 args=parsed(engine)
 assert args.coalesce_window_seconds==.05
 assert args.embodied_harness=='program_gui' and args.native_structured_tools
 assert args.max_actions==500 and args.timeout==0
 command=pool.room_agent_command(args,Path('/task'),Path('/room'),'text_rule',None)
 assert Path(command[1])==ROOT/'bootstrap_verified_room.py'
 assert command[command.index('--engine')+1]==engine
 worker=bootstrap.model_worker_command(ROOT/'worker/run.py',args,Path('/room/agent'))
 assert worker[1]==str(ROOT/'worker/run.py')
 assert worker[worker.index('--engine')+1]==engine
@pytest.mark.parametrize('engine',ENGINES)
def test_configuration_reaches_both_startup_stages(engine):
 args=parsed(engine,['--model','configured-model','--effort','high','--context-window','1000000','--compact-tokens','150000','--binary','/native-cli','--codex-model-catalog','/catalog.json','--codex-model-catalog-sha256','a'*64])
 commands=[pool.room_agent_command(args,Path('/task'),Path('/room'),'real',None),bootstrap.model_worker_command(ROOT/'worker/run.py',args,Path('/room/agent'))]
 for command in commands:
  for flag,value in [('--model','configured-model'),('--effort','high'),('--context-window','1000000'),('--compact-tokens','150000'),('--binary','/native-cli'),('--codex-model-catalog','/catalog.json'),('--codex-model-catalog-sha256','a'*64)]:
   assert command[command.index(flag)+1]==value

def test_legacy_codex_flag_spelling():
 args=parsed('codex',['--codex-context-window','1000000','--codex-compact-tokens','150000'])
 assert (args.context_window,args.compact_tokens)==(1000000,150000)
