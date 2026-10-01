"""Launch the GUI simulator with paths rooted in this directory."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
if __name__ == '__main__':
    subprocess.run([sys.executable, str(ROOT / 'simulation_b01/build_scene.py')], check=True)
    os.execv(sys.executable, [sys.executable, str(ROOT / 'embodied_icl/server.py'), *sys.argv[1:]])
