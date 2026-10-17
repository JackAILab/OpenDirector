import json
from pathlib import Path


def load_trajectory(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
