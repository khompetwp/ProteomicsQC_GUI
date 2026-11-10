"""Source-specific QC; retain every input row and use source-specific units."""
from pathlib import Path
import re

import pandas as pd

from . import fragpipe
from .tables import missingness, numeric_column, read_table, scan_files

SOURCES = ("FragPipe", "DIA-NN", "MaxQuant")
LEVELS = {"FragPipe": fragpipe.LEVELS, "DIA-NN": ("Precursor",), "MaxQuant": ("Evidence",)}
DIANN_REQUIRED = ("Run", "Precursor.Id", "Stripped.Sequence", "Protein.Group")
MAXQUANT_REQUIRED = {
    "evidence.txt": ("Raw file", "Sequence", "Type", "Protein group IDs"),
    "msms.txt": ("Raw file", "Sequence"),
    "proteinGroups.txt": ("Protein IDs",),
}


def locate_inputs(source: Path, data_source: str, level: str, excluded=()) -> list[Path]:
    if not source.exists():
        raise FileNotFoundError(f"Input does not exist: {source}")
    if level not in LEVELS[data_source]:
        raise ValueError(f"{data_source} requires level: {', '.join(LEVELS[data_source])}")
    if data_source == "FragPipe":
        if level == "PSM":
            return fragpipe.locate_psm_files(source, excluded)
        if not source.is_file() or source.suffix.lower() != ".tsv":
            raise ValueError("Peptide/Protein modes require a single TSV file.")
        return [source]
    if data_source == "DIA-NN":
        if source.is_file():
            if source.suffix.lower() not in (".parquet", ".tsv"):
                raise ValueError("Select a DIA-NN main report (.parquet or .tsv), not a matrix or library.")
            return [source]
        candidates = [path for path in scan_files(source, excluded)
                      if path.name.lower() in ("report.parquet", "report.tsv")]
        # TSV and Parquet exports in the same directory represent one report.
        candidates = [path for path in candidates if not (path.suffix == ".tsv" and path.with_suffix(".parquet") in candidates)]
        if len(candidates) != 1:
            raise ValueError(f"Found {len(candidates)} DIA-NN main reports. Select one main report file explicitly.")
        return candidates
    folder = source.parent if source.is_file() else source
    if (folder / "txt" / "evidence.txt").is_file():
        folder = folder / "txt"
    files = [folder / name for name in MAXQUANT_REQUIRED]
    missing = [path.name for path in files if not path.is_file()]
    if missing:
        raise ValueError("MaxQuant requires evidence.txt, msms.txt and proteinGroups.txt in one folder. Missing: " + ", ".join(missing))
    return files + [folder / name for name in ("summary.txt", "parameters.txt", "msmsScans.txt") if (folder / name).is_file()]


def validate_columns(frame, required, path):
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name}: missing required columns: {', '.join(sorted(missing))}")


def audit_numbers(frame, path, columns):
    records = []
    for column in columns:
        present = column in frame
        raw = frame[column] if present else pd.Series(pd.NA, index=frame.index)
        values = numeric_column(raw)
        records.append({"source_file": str(path), "column": column, "column_present": present,
                        "total_rows": len(frame), "valid_numeric_rows": int(values.notna().sum()),
                        "missing_rows": int(raw.isna().sum()),
                        "invalid_numeric_rows": int((raw.notna() & values.isna()).sum())})
    return records


def numeric_medians(frame, columns):
    output = {}
    for column, label in columns.items():
        if column in frame:
            values = numeric_column(frame[column])
            output[label] = float(values.median()) if values.notna().any() else None
    return output


def diann_counts(frame):
    return {"input_rows": len(frame), "unique_precursors": int(frame["Precursor.Id"].nunique()),
            "unique_peptide_sequences": int(frame["Stripped.Sequence"].nunique()),
            "protein_group_strings": int(frame["Protein.Group"].nunique()),
            **numeric_medians(frame, {"Q.Value": "median_precursor_q_value", "Precursor.Quantity": "median_precursor_quantity",
                                    "Precursor.Charge": "median_charge", "RT": "median_rt_min"})}


def analyze_diann(path, check_cancel):
    check_cancel()
    print(f"Reading DIA-NN main report: {path}", flush=True)
    if path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path, engine="pyarrow")
        for column in frame:
            dtype = frame[column].dtype
            if dtype == object or isinstance(dtype, (pd.StringDtype, pd.CategoricalDtype)):
                frame[column] = frame[column].astype("string").str.strip().replace("", pd.NA)
    else:
        frame = read_table(path)
    if frame.empty:
        raise ValueError(f"{path}: report contains no data rows.")
    validate_columns(frame, DIANN_REQUIRED, path)
    check_cancel()
    common = {"source_file": str(path), "data_source": "DIA-NN", "selected_level": "Precursor"}
    summary = {**common, **diann_counts(frame), "rows": len(frame), "columns": len(frame.columns)}
    if "Decoy" in frame:
        summary["decoy_flagged_rows_retained"] = int(numeric_column(frame.Decoy).eq(1).sum())
    if "Q.Value" in frame:
        summary["rows_q_value_above_0_01_retained"] = int(numeric_column(frame["Q.Value"]).gt(0.01).sum())
    runs = [{**common, "run": run, **diann_counts(group)} for run, group in frame.groupby("Run", dropna=False, sort=False)]
    audit = audit_numbers(frame, path, ("Precursor.Charge", "Q.Value", "PG.Q.Value", "Precursor.Quantity", "RT", "Ms1.Apex.Mz.Delta"))
    return [summary], runs, audit, missingness(frame, path)


def split_identifiers(series):
    identifiers = set()
    for value in series.dropna():
        identifiers.update(item.strip() for item in str(value).split(";") if item.strip())
    return identifiers


def maxquant_counts(frame):
    types = frame["Type"].fillna("")
    transferred = types.isin(("MULTI-MATCH", "ISO-MATCH"))
    direct = types.isin(("MSMS", "ISO-MSMS", "MULTI-MSMS", "MULTI-SECPEP"))
    counts = {"evidence_rows": len(frame), "unique_peptide_sequences": int(frame.Sequence.nunique()),
              "protein_group_ids_referenced": len(split_identifiers(frame["Protein group IDs"])),
              "mbr_evidence_rows": int(transferred.sum()), "direct_evidence_rows": int(direct.sum()),
              "other_or_unknown_type_rows": int((~(transferred | direct)).sum())}
    for column, label in (("Reverse", "reverse_flagged_rows_retained"), ("Potential contaminant", "contaminant_flagged_rows_retained")):
        if column in frame:
            counts[label] = int(frame[column].eq("+").sum())
    return {**counts, **numeric_medians(frame, {"Intensity": "median_intensity", "Retention time": "median_rt_min", "Charge": "median_charge"})}


def analyze_maxquant(files, check_cancel):
    frames, summaries, audit, missing = {}, [], [], []
    for path in files:
        check_cancel()
        print(f"Reading MaxQuant table: {path}", flush=True)
        frame = read_table(path)
        validate_columns(frame, MAXQUANT_REQUIRED.get(path.name, ()), path)
        frames[path.name] = frame
        summary = {"source_file": str(path), "data_source": "MaxQuant", "selected_level": path.stem,
                   "rows": len(frame), "columns": len(frame.columns)}
        if path.name == "evidence.txt":
            summary.update(maxquant_counts(frame))
            audit.extend(audit_numbers(frame, path, ("Charge", "Intensity", "Score", "PEP", "Retention time", "Mass error [ppm]")))
        elif path.name == "msms.txt":
            summary["psm_rows"] = len(frame)
        elif path.name == "proteinGroups.txt":
            summary["protein_group_rows"] = len(frame)
        summaries.append(summary)
        missing.extend(missingness(frame, path))
    evidence, msms = frames["evidence.txt"], frames["msms.txt"]
    runs = []
    for run, group in evidence.groupby("Raw file", dropna=False, sort=False):
        runs.append({"source_file": str(files[0]), "data_source": "MaxQuant", "run": run,
                     **maxquant_counts(group), "psm_rows": int(msms["Raw file"].eq(run).sum())})
    return summaries, runs, audit, missing


def analyze(files, data_source, level, check_cancel):
    if data_source == "DIA-NN":
        return analyze_diann(files[0], check_cancel)
    if data_source == "MaxQuant":
        return analyze_maxquant(files, check_cancel)
    summaries, runs, audit, missing = [], [], [], []
    for path in files:
        check_cancel()
        summary, by_runs, numbers, blanks = fragpipe.analyze_file(path, level)
        summaries.append(summary)
        runs.extend(by_runs)
        audit.extend(numbers)
        missing.extend(blanks)
    return summaries, runs, audit, missing
