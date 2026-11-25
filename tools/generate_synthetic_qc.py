"""Create reproducible, explicitly synthetic DIA-NN and MaxQuant test fixtures.

These are documented-column subsets, not full exports or scientific benchmarks.
No DIA-NN/MaxQuant binary or real experimental data is used.
Requires pandas and pyarrow. Refuses to overwrite an existing output directory.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import shutil

import pandas as pd

SEED = 22002026
DIANN_DOCUMENT = "https://github.com/vdemichev/DiaNN/blob/d16794ef0f6b7d1686c68348d57ef0f3f897072d/README.md#main-output-reference"
MAXQUANT_DOCUMENT = "https://cox-labs.github.io/coxdocs/output_tables.html"
RUNS = [f"SYNTHETIC_HeLa_{index:02}" for index in range(1, 7)]
AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"


def peptide_definitions(rng):
    peptides, seen = [], set()
    while len(peptides) < 60:
        sequence = "".join(rng.choice(AMINO_ACIDS) for _ in range(rng.randint(7, 15))) + rng.choice("KR")
        if sequence in seen:
            continue
        seen.add(sequence)
        index = len(peptides)
        group = index // 5
        protein = f"SYNTH_P{group + 1:04}"
        if group == 10:
            protein = "CON__" + protein
        if group == 11:
            protein = "REV__" + protein
        if group == 0:
            protein += ";SYNTH_P0001_ALT"
        modified = sequence.replace("C", "C(UniMod:4)")
        mq_modified = sequence
        if index % 7 == 0 and "M" in sequence:
            modified = modified.replace("M", "M(UniMod:35)", 1)
            mq_modified = mq_modified.replace("M", "M(ox)", 1)
        peptides.append({"sequence": sequence, "modified": modified,
                         "mq_modified": "_" + mq_modified + "_", "protein": protein,
                         "protein_name": f"SYNTHETIC_PROTEIN_{group + 1:02}",
                         "gene": f"SYNTHGENE{group + 1:02}", "group": group,
                         "reference_rt": rng.uniform(5, 50),
                         "base_quantity": 10 ** rng.uniform(5.5, 7.5)})
    return peptides


def write_tsv(frame, path):
    frame.to_csv(path, sep="\t", index=False, encoding="utf-8", float_format="%.8g", na_rep="")


def diann_fixture(peptides, rng, folder):
    folder.mkdir()
    rows = []
    for run_index, run in enumerate(RUNS):
        for peptide_index, peptide in enumerate(peptides):
            for charge in (2, 3):
                if (peptide_index * 2 + charge + run_index) % 17 == 0:
                    continue  # Known missing observations for parser tests.
                q = 0.025 if (peptide_index + charge + run_index) % 19 == 0 else rng.uniform(0.00001, 0.009)
                factor = rng.uniform(0.94, 1.06)
                quantity = peptide["base_quantity"] * rng.uniform(0.8, 1.2)
                rt = peptide["reference_rt"] + rng.uniform(-0.12, 0.12)
                if run_index == 5:
                    quantity *= 0.45
                    rt += 1.5
                if (peptide_index + charge + run_index) % 47 == 0:
                    quantity = None
                protein = peptide["protein"].replace("REV__", "DECOY_")
                mz = 420 + peptide_index * 5.7 + (charge - 2) * 0.4
                rows.append({
                    "Run": run, "Protein.Group": protein, "Protein.Ids": protein,
                    "Protein.Names": peptide["protein_name"], "Genes": peptide["gene"],
                    "Modified.Sequence": peptide["modified"], "Stripped.Sequence": peptide["sequence"],
                    "Precursor.Id": peptide["modified"] + str(charge), "Precursor.Charge": charge,
                    "Precursor.Lib.Index": peptide_index * 2 + charge - 2,
                    "Precursor.Mz": mz, "Proteotypic": 1, "Decoy": int(peptide["group"] == 11),
                    "Q.Value": q, "PEP": min(0.99, q * 2), "Global.Q.Value": q,
                    "PG.Q.Value": 0.003, "Global.PG.Q.Value": 0.003,
                    "Lib.Q.Value": 0.002, "Lib.PG.Q.Value": 0.003, "Protein.Q.Value": 0.003,
                    "Precursor.Quantity": quantity,
                    "Precursor.Normalised": quantity * factor if quantity is not None else None,
                    "Normalisation.Factor": factor, "PG.MaxLFQ": peptide["base_quantity"] * 3,
                    "RT": rt, "RT.Start": rt - 0.15, "RT.Stop": rt + 0.15,
                    "iRT": peptide["reference_rt"] * 2 - 30,
                    "Predicted.RT": peptide["reference_rt"], "FWHM": 0.12,
                    "Ms1.Area": quantity * 0.65 if quantity is not None else None,
                    "Ms1.Apex.Mz.Delta": mz * rng.uniform(-2, 2) / 1e6,
                    "Quantity.Quality": rng.uniform(0.7, 0.98),
                })
    frame = pd.DataFrame(rows)
    frame.to_parquet(folder / "report.parquet", index=False, engine="pyarrow")
    (folder / "report.log.txt").write_text(
        "SYNTHETIC TEST FIXTURE - not output from a DIA-NN execution\n"
        "DIA-NN 2.2.0\n"
        "Schema target only: main report documented on 2025-05-30.\n"
        "Decoy column represents the optional --report-decoys output.\n"
        "MBR setting: unknown; no per-row MBR provenance is inferred.\n"
        "Generated quantities, q-values and PG.MaxLFQ are arbitrary test values.\n",
        encoding="utf-8")
    return frame


def maxquant_fixture(peptides, rng, folder):
    folder.mkdir(parents=True)
    evidence, msms, scans, summaries = [], [], [], []
    for run_index, run in enumerate(RUNS):
        identified = 0
        for peptide_index, peptide in enumerate(peptides):
            for charge in (2, 3):
                if (peptide_index * 2 + charge + run_index) % 17 == 0:
                    continue
                evidence_id = len(evidence)
                matched = run_index > 0 and (peptide_index + charge + run_index) % 9 == 0
                rt = peptide["reference_rt"] + rng.uniform(-0.12, 0.12) + (1.5 if run_index == 5 else 0)
                intensity = peptide["base_quantity"] * rng.uniform(0.8, 1.2) * (0.45 if run_index == 5 else 1)
                mz = 420 + peptide_index * 5.7 + (charge - 2) * 0.4
                score = None if matched else rng.uniform(55, 150)
                msms_id = "" if matched else len(msms)
                scan_number = 1000 + peptide_index * 6 + charge
                ppm = rng.uniform(-2, 2)
                missed = int(peptide_index % 11 == 0)
                evidence.append({
                    "Sequence": peptide["sequence"], "Modified sequence": peptide["mq_modified"],
                    "Length": len(peptide["sequence"]), "Modifications": "Oxidation (M)" if "(ox)" in peptide["mq_modified"] else "Unmodified",
                    "Proteins": peptide["protein"] + (";SYNTH_P0002" if peptide_index == 0 else ""),
                    "Leading proteins": peptide["protein"],
                    "Leading razor protein": peptide["protein"], "Protein names": peptide["protein_name"],
                    "Gene names": peptide["gene"], "Raw file": run, "Experiment": run,
                    "Type": "MULTI-MATCH" if matched else "MULTI-MSMS", "Charge": charge,
                    "m/z": mz, "Mass": mz * charge - charge * 1.007276,
                    "Mass error [ppm]": ppm, "Mass error [Da]": mz * ppm / 1e6,
                    "Uncalibrated mass error [ppm]": ppm + 1,
                    "Uncalibrated mass error [Da]": mz * (ppm + 1) / 1e6,
                    "Uncalibrated - Calibrated m/z [ppm]": 1.0,
                    "Retention time": rt, "Retention length": 0.3,
                    "Calibrated retention time": rt,
                    "Calibrated retention time start": rt - 0.15,
                    "Calibrated retention time finish": rt + 0.15,
                    "Intensity": intensity, "Score": score,
                    "PEP": None if matched else rng.uniform(0.00001, 0.009),
                    "Missed cleavages": missed, "MS/MS count": 0 if matched else 1,
                    "MS/MS scan number": "" if matched else scan_number,
                    "Reverse": "+" if peptide["group"] == 11 else "",
                    "Potential contaminant": "+" if peptide["group"] == 10 else "",
                    "id": evidence_id, "Protein group IDs": "0;1" if peptide_index == 0 else str(peptide["group"]),
                    "Peptide ID": peptide_index, "Mod. peptide ID": peptide_index,
                    "MS/MS IDs": msms_id, "Best MS/MS": msms_id,
                })
                if not matched:
                    msms.append({"id": msms_id, "Sequence": peptide["sequence"],
                                 "Modified sequence": peptide["mq_modified"], "Proteins": peptide["protein"],
                                 "Raw file": run, "Scan number": scan_number, "Charge": charge,
                                 "Retention time": rt, "Score": score, "PEP": evidence[-1]["PEP"],
                                 "Evidence ID": evidence_id, "Peptide ID": peptide_index,
                                 "Missed cleavages": missed})
                    scans.append({"Raw file": run, "Scan number": scan_number,
                                  "Retention time": rt, "Ion injection time": rng.uniform(10, 45),
                                  "Scan event number": 1, "MS/MS ID": msms_id})
                    scans.append({"Raw file": run, "Scan number": 100000 + scan_number,
                                  "Retention time": rt + 0.001, "Ion injection time": rng.uniform(10, 45),
                                  "Scan event number": 1, "MS/MS ID": ""})
                    identified += 1
        summaries.append({"Raw file": run, "Experiment": run, "Fraction": 1,
                          "MS": identified * 3, "MS/MS": identified * 2,
                          "MS/MS submitted": identified * 2, "MS/MS identified": identified,
                          "MS/MS identified [%]": 50.0,
                          "Peptide sequences identified": len({row['Sequence'] for row in evidence if row['Raw file'] == run and row['MS/MS count'] > 0})})
    ev = pd.DataFrame(evidence)
    proteins = []
    for group in range(12):
        subset = ev[ev["Protein group IDs"].map(lambda value: str(group) in value.split(";"))]
        protein = subset.iloc[0]["Proteins"]
        protein = peptides[group * 5]["protein"]
        peptide_count = int(subset.Sequence.nunique())
        counts = ";".join([str(peptide_count)] * (2 if group == 0 else 1))
        entry = {"Protein IDs": protein, "Majority protein IDs": protein,
                 "Protein names": f"SYNTHETIC_PROTEIN_{group + 1:02}", "Gene names": f"SYNTHGENE{group + 1:02}",
                 "Number of proteins": 2 if group == 0 else 1, "Peptides": peptide_count,
                 "Razor + unique peptides": peptide_count, "Unique peptides": peptide_count - 1 if group in (0, 1) else peptide_count,
                 "Peptide counts (all)": counts, "Peptide counts (unique)": counts,
                 "Sequence coverage [%]": 20 + group, "Mol. weight [kDa]": 40 + group,
                 "Score": 100 + group, "Q-value": 0.2 if group == 11 else 0.001,
                 "Intensity": float(subset.Intensity.sum()), "id": group,
                 "Only identified by site": "", "Reverse": "+" if group == 11 else "",
                 "Potential contaminant": "+" if group == 10 else ""}
        for run in RUNS:
            intensity = float(subset.loc[subset["Raw file"] == run, "Intensity"].sum())
            entry["Intensity " + run] = intensity
            entry["LFQ intensity " + run] = intensity * 0.97
            entry["iBAQ " + run] = intensity / 30
        proteins.append(entry)
    total = {"Raw file": "Total", "Experiment": "", "Fraction": ""}
    for key in ("MS", "MS/MS", "MS/MS submitted", "MS/MS identified"):
        total[key] = sum(row[key] for row in summaries)
    total["MS/MS identified [%]"] = 100 * total["MS/MS identified"] / total["MS/MS"]
    total["Peptide sequences identified"] = ev.Sequence.nunique()
    summaries.append(total)
    parameters = pd.DataFrame([
        ("MaxQuant version", "UNSPECIFIED_SYNTHETIC_TEMPLATE"),
        ("Match between runs", "True"), ("Fasta file", "SYNTHETIC_NOT_A_REAL_FASTA.fasta"),
        ("Enzyme", "Trypsin/P"), ("Fixed modifications", "Carbamidomethyl (C)"),
        ("Variable modifications", "Oxidation (M)"),
    ], columns=["Parameter", "Value"])
    scans_frame = pd.DataFrame(scans).sort_values(["Raw file", "Retention time"])
    scans_frame["Scan event number"] = scans_frame.groupby("Raw file").cumcount() % 8 + 1
    frames = {"evidence.txt": ev, "msms.txt": pd.DataFrame(msms),
              "msmsScans.txt": scans_frame, "proteinGroups.txt": pd.DataFrame(proteins),
              "summary.txt": pd.DataFrame(summaries), "parameters.txt": parameters}
    for name, frame in frames.items():
        write_tsv(frame, folder / name)
    return frames


def expected_counts(diann, maxquant):
    evidence = maxquant["evidence.txt"]
    return {
        "diann": {"input_rows_no_filter": len(diann), "runs": diann.Run.nunique(),
                  "unique_precursors_global": diann["Precursor.Id"].nunique(),
                  "unique_stripped_peptides_global": diann["Stripped.Sequence"].nunique(),
                  "protein_group_strings_global": diann["Protein.Group"].nunique(),
                  "decoy_rows": int(diann.Decoy.sum()),
                  "rows_q_value_above_0_01": int((diann["Q.Value"] > 0.01).sum()),
                  "missing_precursor_quantity_rows": int(diann["Precursor.Quantity"].isna().sum()),
                  "rows_per_run": diann.groupby("Run").size().to_dict()},
        "maxquant": {"evidence_rows_no_filter": len(evidence), "runs": evidence["Raw file"].nunique(),
                     "msms_rows": len(maxquant["msms.txt"]),
                     "msms_scan_rows": len(maxquant["msmsScans.txt"]),
                     "protein_groups_no_filter": len(maxquant["proteinGroups.txt"]),
                     "direct_evidence_rows": int((evidence.Type != "MULTI-MATCH").sum()),
                     "mbr_evidence_rows": int((evidence.Type == "MULTI-MATCH").sum()),
                     "reverse_evidence_rows": int((evidence.Reverse == "+").sum()),
                     "contaminant_evidence_rows": int((evidence["Potential contaminant"] == "+").sum()),
                     "rows_per_run": evidence.groupby("Raw file").size().to_dict()},
    }


def generate(destination):
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {destination}")
    destination.mkdir(parents=True)
    shutil.copytree(Path(__file__).resolve().parents[1] / "tests/fixtures/proteome_discoverer",
                    destination / "proteome_discoverer")
    rng = random.Random(SEED)
    peptides = peptide_definitions(rng)
    diann = diann_fixture(peptides, rng, destination / "diann_2_2_0")
    maxquant = maxquant_fixture(peptides, rng, destination / "maxquant_unspecified" / "txt")
    manifest = {
        "synthetic": True, "seed": SEED, "diann_target_version": "2.2.0",
        "maxquant_target_version": "unknown - documented common-column template",
        "source_references": {"diann": DIANN_DOCUMENT, "maxquant": MAXQUANT_DOCUMENT},
        "generator_filters": "None; decoys, contaminants, MBR rows and high-q rows are retained.",
        "known_limits": [
            "No vendor binary was run; this is a representative column subset, not a certified complete export.",
            "Protein sequences, quantities, scores, q-values and statistical provenance are fabricated.",
            "No valid raw spectra, .quant files, spectral libraries, database or ground-truth FDR is supplied.",
            "MaxQuant Type labels model MBR provenance; DIA-NN per-row MBR provenance is not fabricated.",
            "PMultiQC may apply built-in decoy/reverse removal or metric-specific rules.",
            "PMultiQC 0.0.48 was observed to fail evidence parsing when every Protein group IDs value is inferred as an integer; this fixture includes a legitimate multi-group value 0;1. Real numeric-only files need a separate regression test and adapter work.",
            "Synthetic data validates software mechanics only; real output and the target PC still require testing.",
        ],
        "expected_counts": expected_counts(diann, maxquant),
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (destination / "README.md").write_text(
        "# SYNTHETIC TEST DATA / ข้อมูลจำลองสำหรับทดสอบโปรแกรมเท่านั้น\n\n"
        "ชุดนี้สร้างด้วยสคริปต์ ไม่ใช่ผลที่รันจาก DIA-NN หรือ MaxQuant จริง\n"
        "อิงคอลัมน์ DIA-NN 2.2.0 จากเอกสารวันที่ 2025-05-30 และตารางมาตรฐานของ MaxQuant ซึ่งยังไม่ทราบเวอร์ชันเป้าหมาย\n\n"
        "- diann_2_2_0/report.parquet: main-report subset สำหรับทดสอบตัวอ่าน DIA-NN\n"
        "- diann_2_2_0/report.log.txt: log จำลองที่ระบุชัดว่าไม่ใช่การรันจริง\n"
        "- maxquant_unspecified/txt/: evidence, proteinGroups, msms, msmsScans, summary, parameters\n"
        "- manifest.json: seed แหล่งอ้างอิง จำนวนแถวที่คาดหวัง และข้อจำกัด\n\n"
        "มี 6 runs และ 60 peptide sequences; run สุดท้ายถูกจำลองให้สัญญาณลดและ RT เลื่อน\n"
        "จงใจเก็บ decoy/reverse, contaminant, ค่าว่าง, high-q และ MaxQuant MBR เพื่อทดสอบว่าโปรแกรมไม่กรองเองโดยไม่แจ้ง\n"
        "ตัวเลขปริมาณและ q-value เป็นค่าจำลอง ไม่ได้ผ่านการประมาณด้วยอัลกอริทึมของ DIA-NN/MaxQuant\n"
        "การที่ parser อ่านได้หรือ PMultiQC สร้าง HTML ได้ ไม่ยืนยันความถูกต้องกับข้อมูลจริง\n"
        "โปรแกรม GUI รุ่น FragPipe-only ปัจจุบันยังเปิดชุดนี้โดยตรงไม่ได้ ต้องเพิ่ม source adapters ก่อน\n\n"
        f"DIA-NN reference: {DIANN_DOCUMENT}\n\nMaxQuant reference: {MAXQUANT_DOCUMENT}\n",
        encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = generate(args.output)
    print(json.dumps(result["expected_counts"], indent=2))
