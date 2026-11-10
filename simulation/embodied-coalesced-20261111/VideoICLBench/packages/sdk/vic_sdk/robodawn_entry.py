"""Absolute-path, stdlib-only bootstrap for this frozen bounded driver.

This is executed as a file, so an installed or pre-imported older vic_sdk cannot
select the runner. Import path changes affect only this isolated child process.
"""
from pathlib import Path
import importlib
import json
import sys


def main(argv=None):
    package = Path(__file__).resolve().parent
    sdk_root = package.parent
    args=list(sys.argv[1:] if argv is None else argv)
    if '--config' in args:
        index=args.index('--config')
        if index+1>=len(args):raise ValueError('Missing profile path')
        protocol=json.loads(Path(args[index+1]).read_text()).get('protocol')
    elif any(item.startswith('--config=')for item in args):
        protocol=json.loads(Path(next(item.split('=',1)[1]for item in args if item.startswith('--config='))).read_text()).get('protocol')
    elif '--help'in args or '-h'in args:protocol='decision_turn'
    else:raise ValueError('An explicit protocol-bearing --config profile is required')
    if protocol=='decision_turn':module_name='robodawn_turn_runner'
    elif protocol=='legacy_gui_tools':module_name='robodawn_runner'
    else:raise ValueError('Profile must explicitly choose decision_turn or legacy_gui_tools; old checkpoints are not converted')
    expected = package / (module_name+'.py')
    if not expected.is_file():
        raise RuntimeError('Frozen robodawn runner is missing beside its entrypoint')
    # Site hooks and interpreter wrappers can pre-import an ambient SDK before
    # our script runs. Remove only that package family in this child, then pin
    # the exact SDK containing this absolute entrypoint before any SDK import.
    for name in list(sys.modules):
        if name == 'vic_sdk' or name.startswith('vic_sdk.'):
            del sys.modules[name]
    sys.path.insert(0, str(sdk_root))
    importlib.invalidate_caches()
    runner = importlib.import_module('vic_sdk.'+module_name)
    loaded = Path(runner.__file__).resolve()
    loaded_package = Path(sys.modules['vic_sdk'].__file__).resolve()
    if loaded != expected.resolve() or not loaded_package.is_relative_to(package):
        raise RuntimeError('Refusing a robodawn runner outside this frozen SDK')
    return runner.main(args)


if __name__ == '__main__':
    raise SystemExit(main())
