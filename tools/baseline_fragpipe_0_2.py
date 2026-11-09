"""FragPipe table QC with one Excel workbook per run and optional PMultiQC HTML.

Run python msqc_gui.py for the GUI, or:
    python msqc2.py --input data --output results --skip-multiqc
    python msqc2.py --input data/psm.tsv --output results
    python msqc2.py --input peptide.tsv --level Peptide --skip-multiqc

Inputs are never rewritten. GUI QC applies no FDR, decoy, or contaminant filter.
PMultiQC reads original files in the entire scan folder using its own defaults.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import traceback

import pandas as pd

APP_VERSION = "0.2.0"
BASE_DIR = Path(__file__).resolve().parent
LEVELS = ("PSM", "Peptide", "Protein")
NUMERIC_METRICS = {
    "Charge": ("median_charge", "median"),
    "Hyperscore": ("median_hyperscore", "median"),
    "PeptideProphet Probability": ("median_peptideprophet_probability", "median"),
    "Peptide Length": ("median_peptide_length", "median"),
    "Number of Missed Cleavages": ("mean_missed_cleavages", "mean"),
}
MASS_COLUMNS = ("Calibrated Observed M/Z", "Calculated M/Z")
SHEET_NAMES = ("Summary", "By run", "Numeric audit", "Missing values", "Input files", "Run info")


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def scan_files(folder: Path, excluded: tuple[Path, ...] = ()) -> list[Path]:
    """Inventory scan candidates, pruning this application's previous output dirs."""
    def scan_error(error):
        raise error

    found = []
    for current, dirs, files in os.walk(folder, onerror=scan_error):
        current = Path(current)
        dirs[:] = [name for name in sorted(dirs)
                   if name not in (".venv", "__pycache__", "_support")
                   and not any(inside((current / name).resolve(), path) for path in excluded)
                   and not (current / name / "QC_summary.xlsx").is_file()]
        for name in sorted(files):
            path = current / name
            if not any(inside(path.resolve(), parent) for parent in excluded):
                found.append(path)
    return found


def locate_psm_files(source: Path, excluded: tuple[Path, ...] = ()) -> list[Path]:
    if source.is_file():
        if source.name.lower() != "psm.tsv":
            raise ValueError("PSM mode requires a FragPipe file named psm.tsv.")
        return [source]
    if not source.is_dir():
        raise FileNotFoundError(f"Input does not exist: {source}")
    files = [path for path in scan_files(source, excluded) if path.name.lower() == "psm.tsv"]
    if not files:
        raise ValueError(f"No psm.tsv found under: {source}")
    return files


def read_table(file: Path) -> pd.DataFrame:
    # A peptide such as NA is a literal sequence; only blank/whitespace is missing.
    frame = pd.read_csv(file, sep="\t", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if frame.empty:
        raise ValueError(f"{file}: TSV contains no data rows.")
    return frame.apply(lambda column: column.str.strip()).replace("", pd.NA)


def find_column(df: pd.DataFrame, *names: str) -> str | None:
    def key(value):
        return " ".join(value.lower().strip().replace("_", " ").split())
    columns = {key(column): column for column in df.columns}
    return next((columns[key(name)] for name in names if key(name) in columns), None)


def numeric_column(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.mask(values.isin([float("inf"), float("-inf")]))


def summarize_frame(df: pd.DataFrame) -> dict:
    metrics = {
        "psms": len(df),
        "unique_peptide_sequences": int(df["Peptide"].nunique()),
        "missing_peptide_rows": int(df["Peptide"].isna().sum()),
        "missing_peptide_percent": round(float(df["Peptide"].isna().mean() * 100), 3),
    }
    for column, (name, operation) in NUMERIC_METRICS.items():
        if column in df:
            values = numeric_column(df[column])
            metrics[name] = getattr(values, operation)() if values.notna().any() else None
    if set(MASS_COLUMNS).issubset(df.columns):
        observed, calculated = (numeric_column(df[column]) for column in MASS_COLUMNS)
        usable = (observed > 0) & (calculated > 0)
        ppm = numeric_column((observed - calculated) / calculated.where(usable) * 1e6)
        metrics.update({
            "mass_error_valid_rows": int(ppm.notna().sum()),
            "mass_error_excluded_rows": int(ppm.isna().sum()),
            "median_absolute_mass_error_ppm": ppm.abs().median() if ppm.notna().any() else None,
        })
    return metrics


def missingness(df: pd.DataFrame, file: Path) -> list[dict]:
    return [{"source_file": str(file), "column": str(column),
             "missing_count": int(df[column].isna().sum()),
             "missing_percent": round(float(df[column].isna().mean() * 100), 3)}
            for column in df]


def analyze_file(file: Path, level: str) -> tuple[dict, list[dict], list[dict], list[dict]]:
    print(f"Reading: {file}", flush=True)
    df = read_table(file)
    source = {"source_file": str(file)}
    general = {"selected_level": level, "rows": len(df), "columns": len(df.columns),
               "missing_cells_pct": round(float(df.isna().to_numpy().mean() * 100), 3)}
    by_runs, audit = [], []
    if level == "PSM":
        required = {"Peptide", "Charge"} - set(df.columns)
        if required:
            raise ValueError(f"{file}: missing required columns: {sorted(required)}")
        summary = {**source, **general, **summarize_frame(df)}
        for column in (*NUMERIC_METRICS, *MASS_COLUMNS):
            present = column in df
            raw = df[column] if present else pd.Series(pd.NA, index=df.index)
            values = numeric_column(raw)
            entry = {**source, "column": column, "column_present": present,
                     "total_rows": len(df), "valid_numeric_rows": int(values.notna().sum()),
                     "missing_rows": int(raw.isna().sum()),
                     "invalid_numeric_rows": int((raw.notna() & values.isna()).sum())}
            audit.append(entry)
            if not present or entry["missing_rows"] or entry["invalid_numeric_rows"]:
                print(f"WARNING: {file.name}: {column}: present={present}, "
                      f"missing={entry['missing_rows']}, invalid={entry['invalid_numeric_rows']}", flush=True)
        if "Spectrum File" in df:
            for run, group in df.groupby("Spectrum File", dropna=False, sort=False):
                by_runs.append({**source, "run": run, "run_source": "Spectrum File", **summarize_frame(group)})
        else:
            print(f"WARNING: {file}: no Spectrum File column; using parent folder as run.", flush=True)
            by_runs.append({**source, "run": file.parent.name, "run_source": "parent_folder", **summarize_frame(df)})
    else:
        summary = {**source, **general}
        names = (("Peptide", "Peptide Sequence", "Sequence", "Peptide Sequence Modified") if level == "Peptide"
                 else ("Protein", "Protein ID", "Protein ID(s)", "Protein IDs", "Protein Group", "Protein Group ID"))
        column = find_column(df, *names)
        if column:
            label = "unique_peptides" if level == "Peptide" else "unique_protein_identifiers"
            summary[label] = int(df[column].nunique())
        else:
            summary["note"] = "No standard identifier column found; only general table metrics were calculated."
            print("WARNING: " + summary["note"], flush=True)
    return summary, by_runs, audit, missingness(df, file)


def summarize_psm(file: Path) -> tuple[dict, list[dict], list[dict]]:
    summary, runs, audit, _ = analyze_file(file, "PSM")
    return summary, runs, audit


def file_record(path: Path, qc_input: bool, scan_candidate: bool) -> dict:
    stat = path.stat()
    return {"path": str(path), "used_for_gui_qc": qc_input,
            "in_pmultiqc_scan_scope": scan_candidate, "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")}


def save_workbook(outdir: Path, tables: dict[str, pd.DataFrame], info: dict) -> None:
    """Atomic export; identifiers are text, even if they start with '='."""
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    frames = dict(tables)
    frames["Run info"] = pd.DataFrame([{"setting": key, "value": value} for key, value in info.items()])
    book = Workbook(write_only=True)
    fill = PatternFill("solid", fgColor="174B63")
    for name, frame in frames.items():
        if len(frame) > 1_048_575 or len(frame.columns) > 16_384:
            raise ValueError(f"{name} exceeds Excel's sheet size limit.")
        sheet = book.create_sheet(name)
        sheet.freeze_panes = "A2"
        columns = list(frame.columns) or ["note"]
        for index, column in enumerate(columns, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = min(65, max(20, len(str(column)) + 3))
        header = []
        for column in columns:
            cell = WriteOnlyCell(sheet, value=str(column))
            cell.data_type = "s"
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = fill
            header.append(cell)
        sheet.append(header)
        for row in frame.itertuples(index=False, name=None):
            cells = []
            for value in row:
                if pd.isna(value):
                    value = None
                elif hasattr(value, "item"):
                    value = value.item()
                cell = WriteOnlyCell(sheet, value=value)
                if isinstance(value, str):
                    cell.data_type = "s"
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cells.append(cell)
            sheet.append(cells)
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{max(1, len(frame) + 1)}"
    fd, filename = tempfile.mkstemp(prefix=".qc_", suffix=".xlsx", dir=outdir)
    os.close(fd)
    temporary = Path(filename)
    try:
        book.save(temporary)
        temporary.replace(outdir / "QC_summary.xlsx")
    finally:
        temporary.unlink(missing_ok=True)


class Tee:
    def __init__(self, console, log):
        self.console, self.log = console, log

    def write(self, text):
        self.log.write(text)
        if self.console:
            self.console.write(text)
        return len(text)

    def flush(self):
        self.log.flush()
        if self.console:
            self.console.flush()


def run_pmultiqc(source: Path, outdir: Path, excluded: tuple[Path, ...], info: dict) -> bool:
    try:
        installed = version("pmultiqc")
    except PackageNotFoundError:
        raise RuntimeError("PMultiQC is not installed. Excel results are retained; install requirements.txt for HTML.")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", installed)
    if not match or tuple(map(int, match.groups())) < (0, 0, 41):
        raise RuntimeError(f"PMultiQC {installed} is too old; this command requires >=0.0.41.")
    folder = source.parent if source.is_file() else source
    config = {"data_dir_name": "_support", "plots_dir_name": "_support/plots", "no_ai": True}
    command = [sys.executable, "-u", "-m", "multiqc", "--fragpipe-plugin", str(folder),
               "-o", str(outdir), "--filename", "multiqc_report.html", "--no-version-check",
               "--cl-config", json.dumps(config)]
    # Avoid reimporting this application's previous MultiQC reports/data.
    ignored = set(excluded)
    for current, dirs, files in os.walk(folder):
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
    print(f"PMultiQC scans original files in the entire folder: {folder}", flush=True)
    print("Running: " + info["pmultiqc_command"], flush=True)
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    # Use the chosen writable output location for report scratch files as well.
    with tempfile.TemporaryDirectory(prefix=".work_", dir=outdir) as scratch:
        if not inside(Path(scratch).resolve(), outdir.resolve()):
            raise RuntimeError("Unexpected temporary directory outside the run output.")
        environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "TEMP": scratch,
                       "TMP": scratch, "TMPDIR": scratch}
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace", env=environment, **options) as process:
            for line in process.stdout:
                print(line, end="", flush=True)
            code = process.wait()
    info["pmultiqc_exit_code"] = code
    report = outdir / "multiqc_report.html"
    if code != 0 or not report.is_file() or not report.stat().st_size:
        raise RuntimeError(f"PMultiQC report generation failed (exit {code}). Excel results are retained.")
    return True


def run_analysis(source: Path, outdir: Path, level: str = "PSM", html: bool = False,
                 output_root: Path | None = None) -> int:
    if level not in LEVELS:
        raise ValueError(f"Unknown data level: {level}")
    source, outdir = source.resolve(), outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    if any(outdir.iterdir()):
        raise ValueError("The run output directory must be empty; use a fresh directory for each run.")
    folder = source.parent if source.is_file() else source
    excluded = [outdir]
    if output_root and output_root.resolve() != folder and inside(output_root.resolve(), folder):
        excluded.append(output_root.resolve())
    excluded = tuple(excluded)
    info = {
        "application": "FragPipe QC", "application_version": APP_VERSION,
        "started_at": now(), "finished_at": "", "status": "running", "level": level,
        "selected_input": str(source), "output_directory": str(outdir),
        "pmultiqc_requested": html, "pmultiqc_status": "pending" if html else "not requested",
        "pmultiqc_scan_folder": str(folder) if html else "",
        "pmultiqc_scope_note": "Scan candidates are an inventory, not a claim that PMultiQC parsed every file.",
        "gui_processing": "Strip surrounding whitespace; blank values are missing; preserve literal NA; no rows filtered.",
        "gui_filters": "None: no FDR filtering, decoy/contaminant removal, deduplication, or imputation.",
        "pmultiqc_processing": "Original input files; PMultiQC applies its own parsing and metric rules.",
        "unique_peptides_note": "Unique counts are per file/run; summing them is not a global unique count.",
        "mass_error_formula": "1e6 * (Calibrated Observed M/Z - Calculated M/Z) / Calculated M/Z; finite positive m/z pairs only.",
        "numeric_processing": "Non-numeric values and infinities are excluded from numeric statistics; input rows remain counted.",
        "excluded_output_paths": " | ".join(str(path) for path in excluded),
        "python_version": platform.python_version(), "python_executable": sys.executable,
        "operating_system": platform.platform(), "error": "",
    }
    for package in ("pandas", "openpyxl", "pmultiqc", "multiqc"):
        try:
            info[package + "_version"] = version(package)
        except PackageNotFoundError:
            info[package + "_version"] = "not installed"
    tables = {name: pd.DataFrame() for name in SHEET_NAMES if name != "Run info"}
    code = 0
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as log:
        with contextlib.redirect_stdout(Tee(sys.stdout, log)), contextlib.redirect_stderr(Tee(sys.stderr, log)):
            try:
                if html and level != "PSM":
                    raise ValueError("PMultiQC HTML is available in PSM mode only.")
                if level == "PSM":
                    files = locate_psm_files(source, excluded)
                else:
                    if not source.is_file() or source.suffix.lower() != ".tsv":
                        raise ValueError("Peptide/Protein modes require a single TSV file.")
                    files = [source]
                inventory = scan_files(folder, excluded) if html else files
                all_files = sorted(set(files) | set(inventory))
                records = [file_record(path, path in files, html and path in inventory) for path in all_files]
                tables["Input files"] = pd.DataFrame(records)
                info["input_file_count"] = len(files)
                info["pmultiqc_scan_candidate_count"] = len(inventory) if html else 0
                print(f"Found {len(files)} QC input file(s).", flush=True)
                summaries, runs, audit, missing = [], [], [], []
                for file in files:
                    summary, by_runs, numeric_audit, missing_columns = analyze_file(file, level)
                    summaries.append(summary)
                    runs.extend(by_runs)
                    audit.extend(numeric_audit)
                    missing.extend(missing_columns)
                tables.update({"Summary": pd.DataFrame(summaries), "By run": pd.DataFrame(runs),
                               "Numeric audit": pd.DataFrame(audit), "Missing values": pd.DataFrame(missing)})
                # Save QC before calling the optional external report generator.
                info["status"] = "QC complete; HTML pending" if html else "complete"
                save_workbook(outdir, tables, info)
                if html:
                    try:
                        run_pmultiqc(source, outdir, excluded, info)
                        info["pmultiqc_status"] = "complete"
                        info["status"] = "complete"
                    except Exception as exc:
                        info.update(status="partial", pmultiqc_status="failed", error=str(exc))
                        print("ERROR: " + str(exc), flush=True)
                        code = 1
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
                print("ERROR: Could not save Excel workbook: " + str(exc), flush=True)
                code = 2
            if code:
                log.flush()
                log.seek(0)
                (outdir / "processing.log").write_text(log.read(), encoding="utf-8")
            print(f"RESULT_DIR={outdir}", flush=True)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=BASE_DIR / "data")
    parser.add_argument("--output", type=Path, default=BASE_DIR / "results", help="Parent output folder")
    parser.add_argument("--run-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--level", choices=LEVELS, default="PSM")
    parser.add_argument("--skip-multiqc", action="store_true", help="Create Excel only")
    args = parser.parse_args()
    try:
        import openpyxl  # Fail before processing if the Excel writer is unavailable.
    except ImportError:
        print("ERROR: Excel output requires openpyxl. Install requirements.txt in this Python environment.", file=sys.stderr)
        return 2
    root = args.output.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_dir = args.run_dir.expanduser().resolve() if args.run_dir else Path(tempfile.mkdtemp(prefix=datetime.now().strftime("qc_%Y%m%d_%H%M%S_"), dir=root))
    return run_analysis(args.input.expanduser().resolve(), run_dir, args.level,
                        not args.skip_multiqc and args.level == "PSM", root)


if __name__ == "__main__":
    # Windows Thai consoles may otherwise fail on Unicode PMultiQC log messages.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
