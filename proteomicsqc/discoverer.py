"""mzIdentML summaries: one row per SpectrumIdentificationItem, no QC filtering.

Spectrum arrays are read only by the separate PMultiQC worker, never for Excel.
"""
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd

from .tables import missingness, numeric_column, scan_files

SOURCE = "Proteome Discoverer"
NUMERIC = ("rank", "charge", "experimental_mz", "calculated_mz", "xcorr", "rt_seconds")


def check_xml_root(path, expected):
    with path.open("rb") as handle:
        _, root = next(ET.iterparse(handle, events=("start",)))
    name = root.tag.rsplit("}", 1)[-1]
    if name not in expected:
        raise ValueError(f"{path.name}: expected {' / '.join(expected)} XML, found {name}.")


def locate_inputs(source, excluded=()):
    if source.is_file():
        if source.suffix.lower() != ".mzid":
            raise ValueError("Select a .mzid file or a folder containing .mzid files.")
        files = [source]
    else:
        files = [p for p in scan_files(source, excluded) if p.suffix.lower() == ".mzid"]
    if not files:
        raise ValueError("No .mzid identification files found.")
    return sorted(files)


def spectrum_pairs(files):
    """Same-folder, same-stem pairing, with mzML preferred over MGF."""
    pairs = {}
    for path in files:
        candidates = [p for p in path.parent.iterdir() if p.is_file()
                      and p.stem.casefold() == path.stem.casefold()
                      and p.suffix.lower() in (".mzml", ".mgf")]
        mzml = [p for p in candidates if p.suffix.lower() == ".mzml"]
        chosen = mzml or candidates
        if len(chosen) > 1:
            raise ValueError(f"{path.name}: ambiguous matching spectrum files.")
        pairs[path] = chosen[0] if chosen else None
    return pairs


def preflight(files, html):
    warnings = []
    pairs = spectrum_pairs(files)
    for path, spectrum in pairs.items():
        check_xml_root(path, ("MzIdentML",))
        if spectrum:
            if spectrum.suffix.lower() == ".mzml":
                check_xml_root(spectrum, ("mzML", "indexedmzML"))
        else:
            warnings.append(f"{path.name}: no same-name .mzML/.mgf. Excel identification QC is available; HTML requires a spectrum pair in this app.")
    if html:
        warnings.append("Spectrum arrays are loaded into RAM by PMultiQC. A 2 GB file can require substantially more RAM.")
    warnings.append("PD Excel abundance tables are not imported. XML root/pairing checked, not full XML validation.")
    return warnings


def report_inputs(files):
    """Restrict HTML scope to selected IDs and their pairs, without copying arrays."""
    pairs = spectrum_pairs(files)
    selected, stems = [], set()
    for path, spectrum in pairs.items():
        if spectrum is None:
            raise ValueError(f"{path.name}: HTML requires a same-name .mzML or .mgf in the same folder. Select Excel only until the spectrum file is available.")
        stem = path.stem.casefold()
        if stem in stems:
            raise ValueError("HTML requires unique run basenames across folders; duplicate: " + path.stem)
        stems.add(stem)
        check_xml_root(spectrum, ("mzML", "indexedmzML")) if spectrum.suffix.lower() == ".mzml" else None
        with path.open("rb") as handle:
            for _, elem in ET.iterparse(handle, events=("end",)):
                name = elem.tag.rsplit("}", 1)[-1]
                if name == "SpectraData":
                    referenced = _basename(elem.get("location", ""))
                    if referenced and Path(referenced).stem.casefold() != stem:
                        raise ValueError(f"{path.name}: references {referenced}; this HTML mode requires one matching run per mzid file.")
                if name == "Inputs":
                    break
                elem.clear()
        selected.extend((path.resolve(), spectrum.resolve()))
    return selected


def _basename(value):
    return str(value).replace("\\", "/").rsplit("/", 1)[-1]


def read_items(path, check_cancel):
    proteins, peptides, evidence, spectra, records = {}, {}, {}, {}, []
    namespace = None
    with path.open("rb") as handle:
        # Clear completed large entries, keeping their reference maps. No binary spectra.
        stack = []
        for event, elem in ET.iterparse(handle, events=("start", "end")):
            if event == "start":
                stack.append(elem)
                if namespace is None:
                    if elem.tag.rsplit("}", 1)[-1] != "MzIdentML":
                        raise ValueError(f"{path.name}: not an mzIdentML document.")
                    namespace = elem.tag.rsplit("}", 1)[0] + "}"
                continue
            name = elem.tag.rsplit("}", 1)[-1]
            q = lambda tag: namespace + tag
            remove = False
            if name == "DBSequence":
                proteins[elem.get("id")] = elem.get("accession")
                remove = True
            elif name == "Peptide":
                peptides[elem.get("id")] = elem.findtext(q("PeptideSequence"))
                remove = True
            elif name == "PeptideEvidence":
                evidence[elem.get("id")] = (elem.get("dBSequence_ref"), elem.get("isDecoy"))
                remove = True
            elif name == "SpectraData":
                spectra[elem.get("id")] = elem.get("location", "")
            elif name == "SpectrumIdentificationResult":
                check_cancel()
                spec_ref = elem.get("spectraData_ref")
                if spec_ref not in spectra:
                    raise ValueError(f"{path.name}: unresolved SpectraData reference: {spec_ref}")
                rt = next((p for p in elem.findall(q("cvParam"))
                           if p.get("accession") in ("MS:1000894", "MS:1000016")), None)
                rt_value = rt.get("value") if rt is not None else None
                rt_unit = rt.get("unitAccession", "unspecified") if rt is not None else "missing"
                try:
                    rt_seconds = float(rt_value) * {"UO:0000010": 1, "UO:0000031": 60}[rt_unit]
                except (TypeError, ValueError, KeyError):
                    rt_seconds = None
                for item in elem.findall(q("SpectrumIdentificationItem")):
                    pep_ref = item.get("peptide_ref")
                    if pep_ref not in peptides:
                        raise ValueError(f"{path.name}: unresolved peptide reference: {pep_ref}")
                    accessions, decoys = set(), []
                    for ref in item.findall(q("PeptideEvidenceRef")):
                        key = ref.get("peptideEvidence_ref")
                        if key not in evidence or evidence[key][0] not in proteins:
                            raise ValueError(f"{path.name}: unresolved peptide/protein evidence: {key}")
                        protein, decoy = evidence[key]
                        if proteins[protein]:
                            accessions.add(proteins[protein])
                        decoys.append(decoy)
                    scores = {p.get("accession"): p.get("value") for p in item.findall(q("cvParam"))}
                    records.append({"run": spec_ref, "spectrum_id": elem.get("spectrumID"),
                                    "peptide_sequence": peptides[pep_ref],
                                    "protein_accessions": ";".join(sorted(accessions)) or None,
                                    "rank": item.get("rank"), "pass_threshold": item.get("passThreshold"),
                                    "any_decoy_evidence": any(v in ("true", "1") for v in decoys),
                                    "charge": item.get("chargeState"),
                                    "experimental_mz": item.get("experimentalMassToCharge"),
                                    "calculated_mz": item.get("calculatedMassToCharge"),
                                    "xcorr": scores.get("MS:1001155"),
                                    "rt_value": rt_value, "rt_unit": rt_unit, "rt_seconds": rt_seconds})
                remove = True
            if remove:
                if len(stack) > 1:
                    stack[-2].remove(elem)
                elem.clear()
            stack.pop()
    if not records:
        raise ValueError(f"{path.name}: no SpectrumIdentificationItem records found.")
    return pd.DataFrame(records), spectra


def counts(frame):
    protein_ids = {p for value in frame.protein_accessions.dropna() for p in value.split(";")}
    passed = frame.pass_threshold.isin(("true", "1"))
    result = {"psm_items": len(frame),
              "spectra_with_items": len(frame[["run", "spectrum_id"]].drop_duplicates()),
              "unique_peptide_sequences": int(frame.peptide_sequence.nunique()),
              "referenced_protein_accessions": len(protein_ids),
              "rank1_passing_items": int((numeric_column(frame["rank"]).eq(1) & passed).sum()),
              "pass_threshold_false_items_retained": int(frame.pass_threshold.isin(("false", "0")).sum()),
              "any_decoy_evidence_items_retained": int(frame.any_decoy_evidence.sum()),
              "rt_items_with_unspecified_unit": int(frame.rt_unit.eq("unspecified").sum())}
    for column in ("charge", "xcorr", "rt_seconds"):
        values = numeric_column(frame[column])
        result["median_" + column] = float(values.median()) if values.notna().any() else None
    observed, calculated = (numeric_column(frame[c]) for c in ("experimental_mz", "calculated_mz"))
    valid = (observed > 0) & (calculated > 0)
    ppm = numeric_column(1e6 * (observed - calculated) / calculated.where(valid))
    result["mass_error_valid_items"] = int(ppm.notna().sum())
    result["median_absolute_mass_error_ppm"] = float(ppm.abs().median()) if ppm.notna().any() else None
    return result


def analyze(files, check_cancel):
    from .adapters import audit_numbers
    summaries, runs, audit, missing = [], [], [], []
    pairs = spectrum_pairs(files)
    for path in files:
        check_cancel()
        print(f"Reading mzIdentML identification items: {path}", flush=True)
        frame, spectra = read_items(path, check_cancel)
        common = {"source_file": str(path), "data_source": SOURCE, "selected_level": "Identification"}
        summaries.append({**common, **counts(frame), "rows": len(frame),
                          "paired_spectrum_file": str(pairs[path] or ""),
                          "count_note": "All identification items retained; accessions are referenced proteins, not inferred protein groups."})
        for run, group in frame.groupby("run", sort=False):
            runs.append({**common, "run": _basename(spectra[run]) or run,
                         "spectra_data_id": run, **counts(group)})
        audit.extend(audit_numbers(frame, path, NUMERIC))
        missing.extend(missingness(frame, path))
    return summaries, runs, audit, missing
