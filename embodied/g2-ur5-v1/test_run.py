"""Offline launch preparation regressions. No simulator, CLI or API is started."""
import importlib.util
import json
from pathlib import Path
import pytest


@pytest.fixture
def launcher():
    spec = importlib.util.spec_from_file_location('g2_handoff_run', Path(__file__).with_name('run.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def arguments(tmp_path):
    return ['run.py', '--task', 'E04', '--variant', 'A', '--native-python', '/unused/native-python',
            '--gui-python', '/unused/gui-python', '--binary', '/unused/codex',
            '--credentials', '/unused/private-provider.json', '--ca-bundle', '/unused/ca.pem',
            '--out', str(tmp_path / 'trial')]


def test_preview_then_real_reuses_identical_files(launcher, tmp_path, monkeypatch, capsys):
    args = arguments(tmp_path)
    monkeypatch.setattr(launcher.sys, 'argv', args + ['--print-command'])
    assert launcher.main() == 0
    capsys.readouterr()
    directory = tmp_path / '.trial-launch'
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    called = []
    monkeypatch.setattr(launcher.subprocess, 'call', lambda cmd, **kwargs: called.append((cmd, kwargs)) or 0)
    monkeypatch.setattr(launcher.sys, 'argv', args)
    assert launcher.main() == 0
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before
    cmd, kwargs = called[0]
    assert cmd == json.loads(before['launch.json'])['command']
    for option, value in [('--max-actions', '500'), ('--timeout', '0'),
                          ('--codex-context-window', '1050000'), ('--codex-compact-tokens', '945000')]:
        assert cmd[cmd.index(option) + 1] == value
    assert '--embodied-auto-recover' in cmd
    assert kwargs['env']['VIDEOICL_G2_ROOT'] == str(launcher.ROOT)
    assert not (tmp_path / 'trial').exists()


def test_changed_preview_is_rejected_without_overwrite(launcher, tmp_path, monkeypatch):
    args = arguments(tmp_path) + ['--print-command']
    monkeypatch.setattr(launcher.sys, 'argv', args)
    launcher.main()
    directory = tmp_path / '.trial-launch'
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    monkeypatch.setattr(launcher.sys, 'argv', args + ['--max-actions', '499'])
    with pytest.raises(SystemExit, match='2'):
        launcher.main()
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


@pytest.mark.parametrize('target', ['directory', 'cases.json', 'launch.json'])
def test_symlink_launch_is_rejected(launcher, tmp_path, monkeypatch, target):
    directory = tmp_path / '.trial-launch'
    if target == 'directory':
        real = tmp_path / 'unrelated'
        real.mkdir()
        directory.symlink_to(real, target_is_directory=True)
    else:
        directory.mkdir()
        real = tmp_path / 'unrelated'
        real.write_text('unrelated bytes')
        (directory / target).symlink_to(real)
    monkeypatch.setattr(launcher.sys, 'argv', arguments(tmp_path) + ['--print-command'])
    with pytest.raises(SystemExit, match='2'):
        launcher.main()
    if target == 'directory':
        assert not list(real.iterdir())
    else:
        assert real.read_text() == 'unrelated bytes'


def test_existing_trial_is_rejected(launcher, tmp_path, monkeypatch):
    (tmp_path / 'trial').mkdir()
    monkeypatch.setattr(launcher.sys, 'argv', arguments(tmp_path))
    with pytest.raises(SystemExit, match='2'):
        launcher.main()
    assert not (tmp_path / '.trial-launch').exists()


@pytest.mark.parametrize('engine', ['gemini', 'dsh', 'zcode', 'kimi'])
def test_extra_cli_preview_has_native_context_without_codex_relay(launcher, tmp_path, monkeypatch, engine):
    args = arguments(tmp_path)
    index = args.index('--ca-bundle')
    del args[index:index+2]
    args += ['--engine', engine, '--binary', '/unused/'+engine,
             '--model', 'explicit-native-model', '--print-command']
    monkeypatch.setattr(launcher.sys, 'argv', args)
    assert launcher.main() == 0
    record = json.loads((tmp_path/'.trial-launch/launch.json').read_text())
    command = record['command']
    assert command[command.index('--engine')+1] == engine
    assert command[command.index('--native-context-window')+1] == '1050000'
    assert command[command.index('--native-compact-tokens')+1] == '945000'
    assert command[command.index('--timeout')+1] == '0'
    assert not {'--provider-ca-bundle', '--embodied-auto-recover', '--codex-model-catalog'} & set(command)
    assert not (tmp_path/'trial').exists()


def test_extra_cli_cannot_silently_use_codex_recovery(launcher, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher.sys, 'argv', arguments(tmp_path)+['--engine', 'dsh',
        '--model', 'explicit-model', '--auto-recover', '--print-command'])
    with pytest.raises(SystemExit, match='2'):
        launcher.main()
    assert not (tmp_path/'.trial-launch').exists()
