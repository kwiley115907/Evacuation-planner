from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def save_project(project_dir: str | Path, name: str, data: Dict[str, Any]) -> Path:
    """
    Saves JSON project data to streamlit_app/projects/<name>.json
    """
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    safe = "".join(ch for ch in name if ch.isalnum() or ch in ("-", "_")).strip() or "project"
    path = project_dir / f"{safe}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_project(path: str | Path) -> Dict[str, Any]:
    """
    Loads JSON project data.
    """
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))
