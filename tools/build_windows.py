"""Build a portable Windows app with a private, application-local CPython runtime.

Run using the virtual environment containing the pinned QC dependencies.
The build keeps package metadata, DLLs and plugin assets intact. No global Python
installation or PATH change is required on the destination computer.
"""
import argparse
from importlib import metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def build(destination):
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing build: {destination}")
    destination.mkdir(parents=True)
    runtime = destination / "_internal" / "python"
    runtime.mkdir(parents=True)
    base = Path(sys.base_prefix)
    for name in ("python.exe", "pythonw.exe", "python313.dll", "python3.dll", "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
        source = base / name
        if source.is_file():
            shutil.copy2(source, runtime / name)
    for name in ("DLLs", "Lib", "tcl"):
        shutil.copytree(base / name, runtime / name,
                        ignore=shutil.ignore_patterns("site-packages", "__pycache__", "test", "tests", "idlelib", "ensurepip"))
    packages = Path(sys.prefix) / "Lib" / "site-packages"
    shutil.copytree(packages, runtime / "Lib" / "site-packages",
                    ignore=shutil.ignore_patterns("__pycache__", "tests", "test"))
    application = destination / "_internal" / "app"
    application.mkdir()
    shutil.copytree(ROOT / "proteomicsqc", application / "proteomicsqc", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("msqc_gui.py", "msqc2.py"):
        shutil.copy2(ROOT / name, application / name)
    shutil.copy2(ROOT / "README.md", destination / "README.md")
    shutil.copytree(ROOT / "sample_data" / "synthetic_qc", destination / "Examples" / "SYNTHETIC_ONLY")
    compiler = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
    subprocess.run([str(compiler), "/nologo", "/target:winexe", "/platform:x64", "/optimize+",
                    "/reference:System.Windows.Forms.dll", f"/out:{destination / 'ProteomicsQC.exe'}",
                    str(ROOT / "packaging" / "Launcher.cs")], check=True)
    versions = {dist.metadata["Name"]: dist.version for dist in metadata.distributions() if dist.metadata.get("Name")}
    (destination / "_internal" / "environment.json").write_text(json.dumps({"python": sys.version, "packages": versions}, indent=2), encoding="utf-8")
    (destination / "_internal" / "requirements-lock.txt").write_text("\n".join(f"{name}=={value}" for name, value in sorted(versions.items())) + "\n", encoding="utf-8")
    (destination / "THIRD_PARTY_NOTICES.txt").write_text(
        "This application redistributes CPython and Python packages.\n"
        "CPython license: _internal/python/LICENSE.txt\n"
        "Package licenses and notices: _internal/python/Lib/site-packages/*.dist-info/\n"
        "The bundled environment and versions are listed in _internal/environment.json.\n"
        "Synthetic examples are not experimental results and are not outputs of a DIA-NN or MaxQuant execution.\n",
        encoding="utf-8")
    return destination


def refresh_app(destination):
    destination = destination.resolve()
    if not (destination / "ProteomicsQC.exe").is_file() or not (destination / "_internal" / "python" / "python.exe").is_file():
        raise ValueError("Refresh requires an existing ProteomicsQC portable build.")
    application = destination / "_internal" / "app"
    shutil.copytree(ROOT / "proteomicsqc", application / "proteomicsqc", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("msqc_gui.py", "msqc2.py"):
        shutil.copy2(ROOT / name, application / name)
    shutil.copy2(ROOT / "README.md", destination / "README.md")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "ProteomicsQC_0.3.0")
    parser.add_argument("--refresh-app", action="store_true", help="Refresh code/docs in an existing development build; dependencies unchanged")
    args = parser.parse_args()
    print(refresh_app(args.output) if args.refresh_app else build(args.output), flush=True)
