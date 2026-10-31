# Ensure the repo root is importable when running pytest from a checkout
# (equivalent to `pip install -e .` for this flat layout).
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
