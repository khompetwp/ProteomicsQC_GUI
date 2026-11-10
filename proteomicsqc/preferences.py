"""One per-user settings file; no input contents or analysis results are stored."""
import json
import os
from pathlib import Path
import tempfile


def settings_file():
    override = os.environ.get("PROTEOMICSQC_SETTINGS")
    return Path(override) if override else Path(os.environ.get("LOCALAPPDATA", Path.home() / ".config")) / "ProteomicsQC" / "settings.json"


def load_settings():
    try:
        data = json.loads(settings_file().read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {key: data[key] for key in ("input_folder", "output_folder") if isinstance(data.get(key), str)}
    except (OSError, ValueError, TypeError):
        return {}


def save_settings(data):
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {key: str(data[key]) for key in ("input_folder", "output_folder") if data.get(key)}
    fd, name = tempfile.mkstemp(prefix=".settings_", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(clean, stream, ensure_ascii=False, indent=2)
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)
