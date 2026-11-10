"""Run PMultiQC in an isolated subprocess, preserving original input files."""
from importlib.metadata import version
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading

from .tables import inside

PLUGIN_FLAGS = {"FragPipe": "--fragpipe-plugin", "DIA-NN": "--diann-plugin", "MaxQuant": "--maxquant-plugin"}


def validate_report(outdir, messages, info):
    report = outdir / "multiqc_report.html"
    state = outdir / "_support" / "multiqc_data.json"
    if not report.is_file() or not report.stat().st_size or not state.is_file():
        raise RuntimeError("PMultiQC did not create a report with supporting data. Excel QC is retained.")
    data = json.loads(state.read_text(encoding="utf-8"))
    plots = data.get("report_plot_data", {})
    info["pmultiqc_plot_count"] = len(plots)
    if not plots:
        raise RuntimeError("PMultiQC report has no plots. Check input recognition; Excel QC is retained.")
    failures = [line.strip() for line in messages if any(marker in line for marker in (
        "Error occurred while reading", "Error occurred while draw", "Traceback (most recent call last)",
        "encountered an error and was skipped", "DIANN report not found", "Required input not found: psm.tsv", "No FragPipe files found."))]
    if failures:
        info["pmultiqc_parser_errors"] = " | ".join(dict.fromkeys(failures))
        raise RuntimeError("PMultiQC created HTML but some input sections failed to parse. See processing.log; Excel QC is retained.")


def run_pmultiqc(source, files, outdir, excluded, data_source, info, check_cancel):
    installed = version("pmultiqc")
    if tuple(int(part) for part in installed.split(".")[:3]) < (0, 0, 41):
        raise RuntimeError("PMultiQC >=0.0.41 is required for the supported plugins.")
    folder = files[0].parent if data_source == "MaxQuant" else (source.parent if source.is_file() else source)
    config = {"data_dir_name": "_support", "plots_dir_name": "_support/plots", "no_ai": True}
    if data_source == "DIA-NN":
        selected = files[0]
        config["sp"] = {
            "pmultiqc/diann_report_parquet": {"fn": selected.name if selected.suffix.lower() == ".parquet" else "__no_parquet_selected__", "num_lines": 0},
            "pmultiqc/diann_report_tsv": {"fn": selected.name if selected.suffix.lower() == ".tsv" else "__no_tsv_selected__", "num_lines": 0},
        }
        folder = selected.parent
    command = [sys.executable, "-X", "utf8", "-u", str(Path(__file__).with_name("multiqc_runner.py")), PLUGIN_FLAGS[data_source], str(folder),
               "-o", str(outdir), "--filename", "multiqc_report.html", "--no-version-check", "--cl-config", json.dumps(config)]
    ignored = set(excluded)
    for current, dirs, _ in os.walk(folder):
        current = Path(current)
        for name in list(dirs):
            path = (current / name).resolve()
            if name in (".venv", "__pycache__", "_support") or any(inside(path, item) for item in ignored) or (path / "QC_summary.xlsx").is_file():
                ignored.add(path)
                dirs.remove(name)
    for path in sorted(ignored):
        command.extend(["--ignore", path.as_posix(), "--ignore", path.as_posix() + "/*"])
        if os.name == "nt":
            command.extend(["--ignore", str(path), "--ignore", str(path / "*")])
    info["pmultiqc_command"] = subprocess.list2cmdline(command)
    print(f"PMultiQC scan folder: {folder}", flush=True)
    print("PMultiQC uses its own metric-specific rules; the Excel summary retains all input rows.", flush=True)
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    messages, output = [], queue.Queue()
    with tempfile.TemporaryDirectory(prefix=".work_", dir=outdir) as scratch:
        if Path(scratch).resolve().parent != outdir.resolve():
            raise RuntimeError("Invalid report scratch directory.")
        environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "TEMP": scratch, "TMP": scratch, "TMPDIR": scratch}
        # Pass exact PSM paths separately from optional folder-wide supporting files.
        environment.pop("PROTEOMICSQC_PSM_INPUTS", None)
        if data_source == "FragPipe":
            environment["PROTEOMICSQC_PSM_INPUTS"] = json.dumps([str(path.resolve()) for path in files])
            info["pmultiqc_selected_psm_files"] = " | ".join(str(path) for path in files)
        with subprocess.Popen(command, cwd=outdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace", env=environment, **options) as process:
            def read_output():
                for line in process.stdout:
                    output.put(line)
                output.put(None)
            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            try:
                ended = False
                while not ended:
                    check_cancel()
                    try:
                        line = output.get(timeout=0.15)
                    except queue.Empty:
                        continue
                    if line is None:
                        ended = True
                    else:
                        messages.append(line)
                        print(line, end="", flush=True)
                code = process.wait()
            except BaseException:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise
            finally:
                reader.join(timeout=5)
    info["pmultiqc_exit_code"] = code
    if code:
        raise RuntimeError(f"PMultiQC failed (exit {code}). Excel QC is retained.")
    # These are auxiliary exports, not files the HTML needs at its top level.
    support = outdir / "_support"
    support.mkdir(exist_ok=True)
    for name in ("diann_qc.mzQC", "maxquant_qc.mzQC", "experimental_design.tsv"):
        artifact = outdir / name
        if artifact.is_file():
            artifact.replace(support / name)
    validate_report(outdir, messages, info)
