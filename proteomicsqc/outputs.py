"""Create fresh result directories, including user-selected Windows folder names."""
from datetime import datetime
from pathlib import Path
import re
import tempfile


def validate_report_name(name):
    if not name:
        return ""
    if name != name.strip() or name.endswith("."):
        raise ValueError("Report folder name cannot start/end with spaces or end with a dot.")
    if name in (".", "..") or re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise ValueError("Use a folder name only, without path separators or Windows special characters.")
    if re.fullmatch(r"(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])", name.split(".")[0].rstrip(), re.IGNORECASE):
        raise ValueError("This folder name is reserved by Windows. Please choose another name.")
    if len(name.encode("utf-16-le")) // 2 > 120:
        raise ValueError("Report folder name is too long (maximum 120 characters).")
    return name


def create_run_directory(root, name=""):
    name = validate_report_name(name)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if not name:
        return Path(tempfile.mkdtemp(prefix=datetime.now().strftime("qc_%Y%m%d_%H%M%S_"), dir=root))
    directory = root / name
    try:
        directory.mkdir()
    except FileExistsError:
        raise ValueError(f"Report folder already exists. Choose a new name: {directory}") from None
    return directory
