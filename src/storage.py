"""Atomic persistent state. Corrupt state is an explicit error."""
import json
from pathlib import Path


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    temp.replace(path)
