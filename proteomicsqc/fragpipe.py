"""FragPipe metrics retained from the verified 0.2.0 engine."""
from pathlib import Path
import pandas as pd
from .tables import scan_files, read_table, find_column, numeric_column, missingness

LEVELS = ("PSM", "Peptide", "Protein")
NUMERIC_METRICS = {
    "Charge": ("median_charge", "median"),
    "Hyperscore": ("median_hyperscore", "median"),
    "PeptideProphet Probability": ("median_peptideprophet_probability", "median"),
    "Peptide Length": ("median_peptide_length", "median"),
    "Number of Missed Cleavages": ("mean_missed_cleavages", "mean"),
}
MASS_COLUMNS = ("Calibrated Observed M/Z", "Calculated M/Z")

def locate_psm_files(source: Path, excluded: tuple[Path, ...] = ()) -> list[Path]:
    if source.is_file():
        if source.suffix.lower() != ".tsv":
            raise ValueError("PSM mode requires a FragPipe TSV file; its filename can be customized.")
        return [source]
    if not source.is_dir():
        raise FileNotFoundError(f"Input does not exist: {source}")
    files = [path for path in scan_files(source, excluded)
             if path.suffix.lower() == ".tsv" and path.stem.lower().startswith("psm")]
    if not files:
        raise ValueError(f"No psm*.tsv found under: {source}. Select a PSM TSV file explicitly if it has another name.")
    return files


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
