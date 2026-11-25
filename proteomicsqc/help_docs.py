"""Locate the newest compatible manual in source and portable app layouts."""
from pathlib import Path
import re


def find_manual(root, application_version):
    current = tuple(int(v) for v in application_version.split("-", 1)[0].split("."))
    found = []
    for folder in (Path(root) / "docs", Path(root) / "output" / "pdf"):
        for path in folder.glob("ProteomicsQC_User_Manual_TH_*.pdf"):
            match = re.fullmatch(r"ProteomicsQC_User_Manual_TH_(\d+)\.(\d+)\.(\d+)\.pdf", path.name)
            if match and path.is_file() and path.stat().st_size:
                version = tuple(int(v) for v in match.groups())
                if version <= current:
                    found.append((version, path))
    # Stable sort prefers docs/ when both locations contain the same version.
    return sorted(found, key=lambda item: item[0], reverse=True)[0][1] if found else None
