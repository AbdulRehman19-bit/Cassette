from __future__ import annotations

import json
from pathlib import Path

from .normalize import normalize
from .schema import Cassette

CASSETTE_EXT = ".cassette.json"


def cassette_path(directory: str | Path, scenario: str) -> Path:
    return Path(directory) / f"{scenario}{CASSETTE_EXT}"


def write_cassette(directory: str | Path, cassette: Cassette) -> Path:
    """Validate, normalize volatile fields, and write `<dir>/<scenario>.cassette.json`."""
    data = cassette.model_dump(mode="json", exclude_unset=True)
    data = normalize({**data, "recordedAt": "<normalized>"})
    Cassette.model_validate(data)  # never write a file we couldn't read back
    path = cassette_path(directory, cassette.scenario)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path


def read_cassette(path: str | Path) -> Cassette:
    return Cassette.model_validate_json(Path(path).read_text(encoding="utf-8"))


def read_scenario(directory: str | Path, scenario: str) -> Cassette:
    return read_cassette(cassette_path(directory, scenario))


def list_cassettes(directory: str | Path) -> list[str]:
    d = Path(directory)
    if not d.is_dir():
        return []
    return sorted(p.name[: -len(CASSETTE_EXT)] for p in d.iterdir() if p.name.endswith(CASSETTE_EXT))
