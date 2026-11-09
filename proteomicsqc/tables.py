"""Shared table reading, input inventory, and compact Excel export."""
from datetime import datetime
from pathlib import Path
import os
import tempfile
import pandas as pd

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


def missingness(df: pd.DataFrame, file: Path) -> list[dict]:
    return [{"source_file": str(file), "column": str(column),
             "missing_count": int(df[column].isna().sum()),
             "missing_percent": round(float(df[column].isna().mean() * 100), 3)}
            for column in df]


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
