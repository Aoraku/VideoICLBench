"""Forward the previous harness entry point to simulator/harness/coalesced."""
from pathlib import Path
import runpy


if __name__ == "__main__":
    entry = Path(__file__).resolve().parents[2] / "simulator/harness/coalesced" / 'pool_verified.py'
    runpy.run_path(str(entry), run_name="__main__")
