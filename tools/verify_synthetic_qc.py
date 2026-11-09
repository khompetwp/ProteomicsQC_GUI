"""Check synthetic fixture counts, cross-file links and PMultiQC interoperability."""
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pandas as pd

from generate_synthetic_qc import expected_counts

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "sample_data" / "synthetic_qc"


def validate_tables():
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    diann = pd.read_parquet(DATA / "diann_2_2_0" / "report.parquet")
    mq = {name: pd.read_csv(DATA / "maxquant_unspecified" / "txt" / name,
                          sep="\t", keep_default_na=False)
          for name in ("evidence.txt", "msms.txt", "proteinGroups.txt", "summary.txt", "msmsScans.txt")}
    assert expected_counts(diann, mq) == manifest["expected_counts"]
    ev, msms = mq["evidence.txt"], mq["msms.txt"]
    assert ev.id.is_unique and msms.id.is_unique
    assert set(msms["Evidence ID"]).issubset(set(ev.id))
    assert set(msms["Evidence ID"]) == set(ev.loc[ev.Type != "MULTI-MATCH", "id"])
    assert (ev.loc[ev.Type == "MULTI-MATCH", "MS/MS count"] == 0).all()
    assert (ev.loc[ev.Type == "MULTI-MATCH", "MS/MS IDs"] == "").all()
    assert mq["summary.txt"].iloc[-1]["Raw file"] == "Total"
    assert mq["summary.txt"].iloc[-1]["MS/MS identified"] == len(msms)
    assert mq["summary.txt"].iloc[-1]["MS/MS"] == len(mq["msmsScans.txt"])
    assert diann["Q.Value"].gt(0.01).any() and diann.Decoy.eq(1).any()
    assert ev.Reverse.eq("+").any() and ev["Potential contaminant"].eq("+").any()
    return manifest


def generate_report(item):
    source, flag = item
    output_root = ROOT.parent / "tmp" / "synthetic_qc_validation"
    output_root.mkdir(parents=True, exist_ok=True)
    outdir = Path(tempfile.mkdtemp(prefix=source + "_", dir=output_root))
    folder = DATA / source
    command = [sys.executable, "-u", str(ROOT / "proteomicsqc" / "multiqc_runner.py"), flag, str(folder), "-o", str(outdir),
               "--no-version-check", "--cl-config", '{"data_dir_name":"_support","no_ai":true}']
    with tempfile.TemporaryDirectory(prefix=".work_", dir=outdir) as scratch:
        assert Path(scratch).resolve().parent == outdir.resolve()
        environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "TEMP": scratch, "TMP": scratch, "TMPDIR": scratch}
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        with (outdir / "validation.log").open("w", encoding="utf-8") as log:
            process = subprocess.run(command, cwd=outdir, stdout=log, stderr=subprocess.STDOUT,
                                     env=environment, timeout=120, check=False, **options)
    report = outdir / "multiqc_report.html"
    text = (outdir / "validation.log").read_text(encoding="utf-8")
    errors = [line for line in text.splitlines() if "Error occurred" in line or "Traceback" in line or "[ERROR]" in line or "CRITICAL" in line or "encountered an error and was skipped" in line]
    state = outdir / "_support" / "multiqc_data.json"
    plots = len(json.loads(state.read_text(encoding="utf-8")).get("report_plot_data", {})) if state.is_file() else 0
    result = {"source": source, "exit_code": process.returncode,
              "html_created": report.is_file() and report.stat().st_size > 100_000,
              "parser_errors": errors, "plot_count": plots, "output_directory": str(outdir)}
    (outdir / "validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    manifest = validate_tables()
    print("PASS: documented-column subsets, known counts, no filter removal, and MaxQuant cross-file ID links", flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(generate_report, [("diann_2_2_0", "--diann-plugin"),
                                                  ("maxquant_unspecified", "--maxquant-plugin")]))
    print(json.dumps(results, indent=2), flush=True)
    if not all(item["exit_code"] == 0 and item["html_created"] and item["plot_count"] > 0 and not item["parser_errors"] for item in results):
        sys.exit(1)
    manifest["interoperability_check"] = {
        "pmultiqc": version("pmultiqc"), "multiqc": version("multiqc"),
        "synthetic_table_checks": "passed", "both_html_reports_created": True,
        "worker": "application worker with version-scoped dtype compatibility fixes",
        "note": "Synthetic interoperability only; does not validate real DIA-NN/MaxQuant exports or scientific QC."
    }
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
