"""Header-only source validation; never reads complete datasets or filters rows."""
from pathlib import Path
import pandas as pd
from . import adapters


def check_input(source, data_source, level, excluded=(), html=False):
    files = adapters.locate_inputs(Path(source), data_source, level, excluded)
    warnings = []
    for path in files:
        if data_source == "FragPipe":
            required = ("Peptide", "Charge") if level == "PSM" else ()
        elif data_source == "DIA-NN":
            required = adapters.DIANN_REQUIRED
        else:
            required = adapters.MAXQUANT_REQUIRED.get(path.name, ())
        if not required:
            continue
        if path.suffix.lower() == ".parquet":
            import pyarrow.parquet as parquet
            columns = set(parquet.read_schema(path).names)
        else:
            columns = set(pd.read_csv(path, sep="\t", nrows=0, encoding="utf-8-sig").columns)
        missing = set(required) - columns
        if missing:
            raise ValueError(f"{path.name}: missing required columns: {', '.join(sorted(missing))}. Check Data source and Data level.")
        if data_source == "FragPipe" and level == "PSM" and html and "Spectrum" not in columns:
            warnings.append(f"{path.name}: Spectrum is missing; Excel can be created but PMultiQC HTML may fail.")
    return files, warnings
