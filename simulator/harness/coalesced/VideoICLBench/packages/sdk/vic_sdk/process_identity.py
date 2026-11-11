"""Command-only adapter for the new release's same-PID named Python launcher."""
from pathlib import Path

LAUNCHER=Path(__file__).resolve().parents[4]/'process_launcher.py'
DISPLAY_NAME='robodojo-embodiedevo'


def named_python_command(command, identity_dir, role):
    command=list(map(str,command))
    if len(command)<2:raise ValueError('Python interpreter and entrypoint required')
    if not LAUNCHER.is_file():raise ValueError('Named launcher missing from immutable release')
    return [command[0],str(LAUNCHER),'--identity-dir',str(Path(identity_dir).resolve()),
            '--role',str(role),'--',*command[1:]]
