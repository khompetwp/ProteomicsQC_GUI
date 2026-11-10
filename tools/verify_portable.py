"""Exercise the EXE launcher and bundled runtime with host Python paths disabled."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from proteomicsqc import __version__ as VERSION


def run(portable, fragpipe=None):
    launcher = portable / "ProteomicsQC.exe"
    assert (portable / "_internal" / "app" / "docs" / "ProteomicsQC_User_Manual_TH_0.4.0.pdf").is_file(), "Bundled manual missing"
    output_root = ROOT / "build" / "portable_validation"
    output_root.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="portable_validation_", dir=output_root))
    environment = {**os.environ, "PATH": os.path.join(os.environ["SystemRoot"], "System32"),
                   "PYTHONHOME": "INVALID_HOST_PYTHON", "PYTHONPATH": "INVALID_HOST_PACKAGES"}
    check = output / "self_test.json"
    process = subprocess.run([str(launcher), "--self-test", "--output", str(check)], env=environment, timeout=90, check=False)
    assert process.returncode == 0, "EXE startup failed"
    diagnostics = json.loads(check.read_text(encoding="utf-8"))
    assert diagnostics["success"] and diagnostics["gui_created"]
    private_root = portable / "_internal" / "python"
    assert Path(diagnostics["prefix"]).resolve() == private_root.resolve()
    for package in diagnostics["packages"].values():
        assert private_root.resolve() in Path(package["path"]).resolve().parents, package
    cases = [("DIA-NN", "DIA-NN", portable / "Examples" / "SYNTHETIC_ONLY" / "diann_2_2_0" / "report.parquet"),
             ("MaxQuant", "MaxQuant", portable / "Examples" / "SYNTHETIC_ONLY" / "maxquant_unspecified")]
    if fragpipe:
        cases.append(("FragPipe", "FragPipe", fragpipe))
        for filename in ("psm_2.tsv", "HeLa รอบสอง.tsv"):
            renamed_folder = output / ("input_" + Path(filename).stem)
            renamed_folder.mkdir()
            renamed = renamed_folder / filename
            shutil.copyfile(fragpipe, renamed)
            # A neighboring canonical file must never replace the selected PSM.
            (renamed_folder / "psm.tsv").write_text("invalid\nnot a PSM table\n", encoding="utf-8")
            cases.append(("FragPipe-" + Path(filename).stem, "FragPipe", renamed))
    unicode_input = output / "ทดสอบ QC"
    unicode_input.mkdir()
    unicode_report = unicode_input / "report DIA 2.2.parquet"
    shutil.copyfile(cases[0][2], unicode_report)
    cases.append(("DIA-NN-พาธไทย", "DIA-NN", unicode_report))
    results = []
    for label, source, path in cases:
        target = output / label
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        report_name = "HeLa QC รอบสอง" if label.startswith("FragPipe-") else ""
        command = [str(launcher), "--cli", "--source", source, "--input", str(path), "--output", str(target)]
        if report_name:
            command.extend(["--report-name", report_name])
        started = time.monotonic()
        result = subprocess.run(command, env=environment, timeout=180, check=False, capture_output=True)
        folder = target / report_name if report_name else next(target.glob("qc_*"))
        book = folder / "QC_summary.xlsx"
        history = pd.read_excel(book, sheet_name="Run info", keep_default_na=False)
        history = dict(zip(history.setting, history.value))
        assert result.returncode == 0, (source, history.get("error"), folder)
        assert history["status"] == "complete", history
        assert history["pmultiqc_plot_count"] > 0
        assert sorted(path.name for path in folder.iterdir()) == ["QC_summary.xlsx", "_support", "multiqc_report.html"]
        if digest:
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        if report_name:
            summary = pd.read_excel(book, sheet_name="Summary")
            assert Path(summary.iloc[0].source_file) == path
            assert summary.iloc[0].psms == len(pd.read_csv(fragpipe, sep="\t"))
            assert history["pmultiqc_selected_psm_files"] == str(path)
            before = hashlib.sha256(book.read_bytes()).hexdigest()
            repeat = subprocess.run(command, env=environment, timeout=30, check=False, capture_output=True)
            assert repeat.returncode == 2, "A named report must never overwrite an existing report"
            assert hashlib.sha256(book.read_bytes()).hexdigest() == before
        results.append({"source": source, "case": label, "status": "complete", "plot_count": history["pmultiqc_plot_count"],
                        "seconds": round(time.monotonic() - started, 1), "result_directory": str(folder)})
    # Cancel while the HTML phase is starting, and require a persisted cancellation status.
    target = output / "cancel"
    child = subprocess.Popen([str(launcher), "--cli", "--source", "DIA-NN", "--input", str(cases[0][2]), "--output", str(target)], env=environment)
    deadline = time.monotonic() + 45
    directory = None
    while child.poll() is None and time.monotonic() < deadline:
        books = list(target.glob("qc_*/QC_summary.xlsx"))
        if books:
            directory = books[0].parent
            (directory / ".cancel_requested").touch()
            break
        time.sleep(0.05)
    assert directory is not None, "No workbook appeared for the cancellation check"
    assert child.wait(timeout=30) == 130
    history = pd.read_excel(directory / "QC_summary.xlsx", sheet_name="Run info", keep_default_na=False)
    assert dict(zip(history.setting, history.value))["status"] == "cancelled"
    summary = {"host_python_disabled": True, "self_test": diagnostics, "cases": results,
               "cancellation": "passed", "validation_directory": str(output)}
    (output / "verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portable", type=Path, default=ROOT / "dist" / ("ProteomicsQC_" + VERSION))
    parser.add_argument("--fragpipe", type=Path)
    args = parser.parse_args()
    run(args.portable.resolve(), args.fragpipe.resolve() if args.fragpipe else None)
