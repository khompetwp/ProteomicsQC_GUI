"""Multi-source analysis orchestration and run history."""
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
import contextlib
from pathlib import Path
import platform
import sys
import tempfile
import traceback

import pandas as pd

from . import __version__, adapters
from .reporting import run_pmultiqc
from .runtime import Cancelled, cancellation_check
from .tables import Tee, file_record, inside, now, save_workbook, scan_files

SHEET_NAMES = ("Summary", "By run", "Numeric audit", "Missing values", "Input files", "Run info")


def run_analysis(source, outdir, level="PSM", html=False, output_root=None, data_source="FragPipe"):
    if data_source not in adapters.SOURCES:
        raise ValueError("Unsupported data source: " + data_source)
    source, outdir = Path(source).resolve(), Path(outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    if any(path.name != ".cancel_requested" for path in outdir.iterdir()):
        raise ValueError("Each analysis requires a fresh, empty output directory.")
    folder = source.parent if source.is_file() else source
    excluded = [outdir]
    if output_root and Path(output_root).resolve() != folder and inside(Path(output_root).resolve(), folder):
        excluded.append(Path(output_root).resolve())
    excluded = tuple(excluded)
    check_cancel = cancellation_check(outdir)
    info = {
        "application": "ProteomicsQC GUI", "application_version": __version__,
        "started_at": now(), "finished_at": "", "status": "running", "data_source": data_source,
        "level": level, "selected_input": str(source), "output_directory": str(outdir),
        "pmultiqc_requested": html, "pmultiqc_status": "pending" if html else "not requested",
        "pmultiqc_scan_folder": str(folder) if html else "",
        "pmultiqc_scope_note": "Inventory lists scan candidates, not proof that PMultiQC parsed each file. FragPipe uses exactly the selected/discovered PSM files; DIA-NN uses the selected main report only. Optional supporting files are scanned from the folder.",
        "gui_processing": "Trim text; blank cells are missing; preserve literal NA. Retain every input row.",
        "gui_filters": "None: no q-value/FDR filter, decoy/contaminant removal, deduplication, imputation, or renormalisation.",
        "pmultiqc_processing": "Original files with PMultiQC's own metric-specific rules, including decoy/reverse handling. Counts can differ from Excel.",
        "pmultiqc_compatibility": "PMultiQC 0.0.48 only: read dictionary-encoded DIA-NN text labels and numeric MaxQuant group IDs as strings to avoid plugin dtype errors. No filter changes.",
        "counting_unit": {"FragPipe": level, "DIA-NN": "precursor observation per run; not DDA PSMs", "MaxQuant": "evidence features, MS/MS PSM rows, protein-group rows separately"}[data_source],
        "mbr_note": "MaxQuant Type labels are reported as supplied; other/unknown labels remain explicit. DIA-NN per-row MBR provenance is not inferred.",
        "unique_counts_note": "Unique counts are per file/run. Protein-group strings are not counts of individual proteins. Do not sum per-run uniques as a global unique count.",
        "numeric_processing": "Non-numeric and infinite values are excluded from statistics; their rows remain counted.",
        "excluded_output_paths": " | ".join(str(path) for path in excluded),
        "python_version": platform.python_version(), "python_executable": sys.executable,
        "operating_system": platform.platform(), "error": "",
    }
    for package in ("pandas", "openpyxl", "pyarrow", "pmultiqc", "multiqc"):
        try:
            info[package + "_version"] = version(package)
        except PackageNotFoundError:
            info[package + "_version"] = "not installed"
    tables = {name: pd.DataFrame() for name in SHEET_NAMES if name != "Run info"}
    code = 0
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as log:
        with contextlib.redirect_stdout(Tee(sys.stdout, log)), contextlib.redirect_stderr(Tee(sys.stderr, log)):
            try:
                check_cancel()
                if data_source == "FragPipe" and level != "PSM" and html:
                    raise ValueError("FragPipe HTML reporting requires PSM mode.")
                files = adapters.locate_inputs(source, data_source, level, excluded)
                if data_source in ("DIA-NN", "MaxQuant"):
                    folder = files[0].parent
                    info["pmultiqc_scan_folder"] = str(folder) if html else ""
                inventory = scan_files(folder, excluded) if html else files
                tables["Input files"] = pd.DataFrame([file_record(path, path in files, html and path in inventory)
                                                     for path in sorted(set(files) | set(inventory))])
                info["input_file_count"] = len(files)
                info["pmultiqc_scan_candidate_count"] = len(inventory) if html else 0
                summaries, runs, audit, missing = adapters.analyze(files, data_source, level, check_cancel)
                check_cancel()
                tables.update({"Summary": pd.DataFrame(summaries), "By run": pd.DataFrame(runs),
                               "Numeric audit": pd.DataFrame(audit), "Missing values": pd.DataFrame(missing)})
                info["status"] = "QC complete; HTML pending" if html else "complete"
                save_workbook(outdir, tables, info)
                if html:
                    try:
                        run_pmultiqc(source, files, outdir, excluded, data_source, info, check_cancel)
                        info.update(pmultiqc_status="complete", status="complete")
                    except Cancelled:
                        raise
                    except Exception as exc:
                        info.update(status="partial", pmultiqc_status="failed or incomplete", error=str(exc))
                        print("ERROR: " + str(exc), flush=True)
                        code = 1
                check_cancel()
            except Cancelled as exc:
                info.update(status="cancelled", error=str(exc))
                if html and info["pmultiqc_status"] == "pending":
                    info["pmultiqc_status"] = "cancelled or not run"
                print(str(exc), flush=True)
                code = 130
            except Exception as exc:
                info.update(status="failed", error=str(exc))
                if html and info["pmultiqc_status"] == "pending":
                    info["pmultiqc_status"] = "not run (QC failed)"
                traceback.print_exc()
                code = 2
            info["finished_at"] = now()
            try:
                save_workbook(outdir, tables, info)
            except Exception as exc:
                print("ERROR: Could not save the final Excel workbook: " + str(exc), flush=True)
                code = 2
            if code:
                log.flush()
                log.seek(0)
                (outdir / "processing.log").write_text(log.read(), encoding="utf-8")
            (outdir / ".cancel_requested").unlink(missing_ok=True)
            print(f"RESULT_DIR={outdir}", flush=True)
    return code
