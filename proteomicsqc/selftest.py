"""Portable startup check; writes JSON when launched with --self-test --output."""
from importlib import import_module
from importlib.metadata import version
import json
from pathlib import Path
import sys
from . import __version__


def main():
    result = {"application_version": __version__, "python": sys.version.split()[0], "executable": sys.executable,
              "prefix": sys.prefix, "packages": {}, "gui_created": False}
    try:
        for name in ("pandas", "openpyxl", "pyarrow", "pmultiqc", "multiqc", "ttkbootstrap"):
            module = import_module(name)
            result["packages"][name] = {"version": version(name), "path": str(module.__file__)}
        from .gui import MSQCApp
        app = MSQCApp()
        app.withdraw()
        app.update()
        app.destroy()
        result["gui_created"] = True
        result["success"] = True
        code = 0
    except Exception as exc:
        result.update(success=False, error=str(exc))
        code = 2
    text = json.dumps(result, indent=2)
    if "--output" in sys.argv:
        Path(sys.argv[sys.argv.index("--output") + 1]).write_text(text, encoding="utf-8")
    elif sys.stdout:
        print(text)
    return code
