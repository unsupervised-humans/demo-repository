from pathlib import Path
import json

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def load_sample(name: str) -> dict:
    path = SAMPLES / name
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
