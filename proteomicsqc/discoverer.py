"""mzIdentML summaries: one row per SpectrumIdentificationItem, no QC filtering.

Spectrum arrays are read only by the separate PMultiQC worker, never for Excel.
"""
from pathlib import Path
import re
import math
from bisect import bisect_left, bisect_right
from collections import Counter
import xml.etree.ElementTree as ET
import xml.sax
from xml.sax.handler import ContentHandler, feature_namespaces, feature_external_ges
from xml.sax.handler import LexicalHandler, property_lexical_handler

import pandas as pd

from .tables import missingness, numeric_column, scan_files

SOURCE = "Proteome Discoverer"
NUMERIC = ("rank", "charge", "experimental_mz", "calculated_mz", "xcorr", "rt_seconds")

_SCAN_ID = re.compile(r"(?:controllerType=\d+ controllerNumber=\d+ )?scan=(\d+)")


def scan_number(value):
    """Recognize only documented scan-only/Thermo forms; never guess index IDs."""
    match = _SCAN_ID.fullmatch(str(value))
    return int(match.group(1)) if match else None


def _positive_number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (ValueError, TypeError):
        return None


def _seconds(value, unit, name="", *, unitless_minutes=False):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    if unit == "UO:0000010" or name.lower() in ("second", "seconds"):
        return value
    if unit == "UO:0000031" or name.lower() in ("minute", "minutes"):
        return value * 60
    if not unit and not name and unitless_minutes:
        return value * 60
    return None


def _stream_xml(path, handler, check_cancel):
    parser = xml.sax.make_parser()
    parser.setFeature(feature_namespaces, True)
    parser.setFeature(feature_external_ges, False)
    parser.setContentHandler(handler)
    if isinstance(handler, LexicalHandler):
        parser.setProperty(property_lexical_handler, handler)
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            check_cancel()
            parser.feed(chunk)
    parser.close()


def mzml_ms2_metadata(path, check_cancel=lambda: None):
    """Stream metadata without decoding or retaining binary array text.

    This makes one sequential pass through the file. The memory used for the
    index scales with spectrum IDs, rather than the size of the peak arrays.
    """
    class Handler(ContentHandler):
        def __init__(self):
            super().__init__()
            self.rows, self.current, self.level, self.valid_root = [], None, None, False
            self.ions, self.ion = [], None

        def startElementNS(self, name, qname, attrs):
            tag = name[1]
            if not self.valid_root:
                if name[0] != "http://psi.hupo.org/ms/mzml" or tag not in ("mzML", "indexedmzML"):
                    raise ValueError(f"{path.name}: not an mzML document.")
                self.valid_root = True
            if tag == "spectrum":
                self.current = {"native_id": attrs.get((None, "id")), "rt_seconds": None}
                self.level, self.ions, self.ion = None, [], None
                check_cancel()
            elif tag == "selectedIon" and self.current is not None:
                self.ion = {"precursor_mz": None, "charge": None}
            elif tag == "cvParam" and self.current is not None:
                accession = attrs.get((None, "accession"))
                value = attrs.get((None, "value"))
                if accession == "MS:1000511":
                    self.level = attrs.get((None, "value"))
                elif accession == "MS:1000016":
                    self.current["rt_seconds"] = _seconds(value, attrs.get((None, "unitAccession")), attrs.get((None, "unitName"), ""))
                elif self.ion is not None and accession in ("MS:1000744", "MS:1000041"):
                    self.ion["precursor_mz" if accession == "MS:1000744" else "charge"] = _positive_number(value)

        def endElementNS(self, name, qname):
            if name[1] == "selectedIon" and self.ion is not None:
                self.ions.append(self.ion)
                self.ion = None
            elif name[1] == "spectrum":
                if self.level == "2":
                    if not self.current["native_id"]:
                        raise ValueError(f"{path.name}: MS2 spectrum has no native ID.")
                    # Never silently choose one precursor from a multi-ion record.
                    self.current.update(self.ions[0] if len(self.ions) == 1 else {"precursor_mz": None, "charge": None})
                    self.rows.append(self.current)
                self.current, self.level = None, None

    handler = Handler()
    _stream_xml(path, handler, check_cancel)
    if not handler.rows:
        raise ValueError(f"{path.name}: no MS2 spectrum IDs found.")
    return handler.rows


def mzml_ms2_ids(path, check_cancel=lambda: None):
    return [row["native_id"] for row in mzml_ms2_metadata(path, check_cancel)]


def pd_retention_times(path, check_cancel=lambda: None, *, first_scans=None):
    """PD-only policy: explicit units first; unitless PD export RT is minutes.

    The policy is recorded in the matching audit. Matching never changes the
    upstream RT values used by PMultiQC or the Excel summary.
    """
    class Handler(ContentHandler, LexicalHandler):
        def __init__(self):
            self.current, self.value, self.rows, self.unitless = None, None, {}, set()
            self.pd_software = False
            self.pending = None
            self.sources = set()

        def comment(self, content):
            self.pending = re.search(r"\bFileId=(\d+)(?:\s*\([^)]*\))?;\s*FirstScan=(\d+)(?=;|\s*$)", content)

        def startElementNS(self, name, qname, attrs):
            hint, self.pending = self.pending, None
            if name[1] == "AnalysisSoftware":
                if "proteome discoverer" in (attrs.get((None, "id"), "") + " " + attrs.get((None, "name"), "")).lower():
                    self.pd_software = True
            if name[1] == "cvParam" and attrs.get((None, "accession")) == "MS:1000650":
                self.pd_software = True
            if name[1] == "SpectrumIdentificationResult":
                self.current, self.value = attrs.get((None, "spectrumID")), None
                if hint and self.pd_software and first_scans is not None:
                    file_id, number = hint.groups()
                    self.sources.add((file_id, attrs.get((None, "spectraData_ref"))))
                    if len(self.sources) > 1:
                        raise ValueError(f"{path.name}: FirstScan references multiple source files for one mzML pair.")
                    entry = (file_id, int(number))
                    if first_scans.setdefault(self.current, entry) != entry:
                        raise ValueError(f"{path.name}: conflicting FirstScan for {self.current}")
            elif name[1] == "cvParam" and self.current is not None:
                if attrs.get((None, "accession")) in ("MS:1000894", "MS:1000016"):
                    unit, unit_name = attrs.get((None, "unitAccession")), attrs.get((None, "unitName"), "")
                    if not unit and not unit_name:
                        self.unitless.add(self.current)
                    self.value = _seconds(attrs.get((None, "value")), unit, unit_name,
                                          unitless_minutes=self.pd_software)

        def endElementNS(self, name, qname):
            self.pending = None
            if name[1] == "SpectrumIdentificationResult":
                if self.current in self.rows and self.rows[self.current] != self.value:
                    raise ValueError(f"{path.name}: inconsistent RT values for {self.current}")
                self.rows[self.current] = self.value
                self.current, self.value = None, None

    handler = Handler()
    _stream_xml(path, handler, check_cancel)
    return handler.rows, {"unitless_rt_policy": "minutes for identified Proteome Discoverer exports only",
                          "unitless_spectrum_ids": len(handler.unitless), "pd_software_identified": handler.pd_software}


def align_spectrum_ids(frame, metadata_by_run, *, first_scans_by_run=None, rt_tolerance_seconds=0.00006, mz_tolerance_ppm=10):
    """Map accepted plugin rows to actual native MS2 IDs, never between runs.

    Check explicit PD FirstScan against native scan, RT and charge. With no
    FirstScan, require a unique RT, precursor m/z and charge match.
    Repeated PSMs/protein-evidence rows remain repeated; no scientific filtering.
    """
    result = frame.copy()
    audits = []
    for run, group in frame.groupby("filename", sort=False, dropna=False):
        metadata = metadata_by_run.get(run, [])
        hints = (first_scans_by_run or {}).get(run, {})
        by_scan = {}
        exact = set()
        timed = []
        for record in metadata:
            native = record["native_id"]
            if native in exact:
                raise ValueError(f"{run}: duplicate native MS2 ID: {native}")
            exact.add(native)
            if hints:
                by_scan.setdefault(scan_number(native), []).append(record)
            rt = record.get("rt_seconds")
            if rt is not None and math.isfinite(rt) and rt >= 0:
                timed.append(record)
        timed.sort(key=lambda r: r["rt_seconds"])
        times = [r["rt_seconds"] for r in timed]
        mapping = []
        # Repeated peptide/protein evidence rows share the same validated result.
        cache = {}
        for row in group.to_dict("records"):
            original = row["spectrumID"]
            hint = hints.get(original)
            rt, mz, charge = row.get("pd_rt_seconds"), _positive_number(row.get("experimentalMassToCharge")), _positive_number(row.get("chargeState"))
            try:
                rt = float(rt)
            except (ValueError, TypeError):
                rt = float("nan")
            key = (str(original), rt if math.isfinite(rt) else None, mz, charge)
            if key not in cache:
                candidates = []
                reason = "missing_rt_mz_or_charge"
                selected_mz = None
                if hint:
                    candidates = by_scan.get(hint[1], [])
                    reason = "first_scan_not_found"
                    if len(candidates) == 1:
                        candidate = candidates[0]
                        selected_mz = candidate.get("precursor_mz")
                        if (candidate.get("rt_seconds") is None or not math.isfinite(rt)
                                or abs(candidate["rt_seconds"] - rt) > rt_tolerance_seconds
                                or charge is None or not charge.is_integer() or candidate.get("charge") != charge):
                            candidates = []
                            reason = "first_scan_rt_or_charge_mismatch"
                elif math.isfinite(rt) and rt >= 0 and mz is not None and charge is not None and charge.is_integer():
                    candidates_rt = timed[bisect_left(times, rt-rt_tolerance_seconds):bisect_right(times, rt+rt_tolerance_seconds)]
                    candidates = [r for r in candidates_rt
                                  if _positive_number(r.get("precursor_mz")) is not None
                                  and _positive_number(r.get("charge")) == charge
                                  and abs(mz-r["precursor_mz"])/mz*1e6 <= mz_tolerance_ppm]
                    reason = "rt_not_found" if not candidates_rt else "mz_or_charge_mismatch"
                if len(candidates) == 1:
                    target = candidates[0]["native_id"]
                    # A known controller difference must not be stripped away.
                    controller = lambda value: re.match(r"controllerType=\d+ controllerNumber=\d+", str(value))
                    a, b = controller(original), controller(target)
                    if a and b and a.group() != b.group():
                        target, reason = None, "controller_mismatch"
                    else:
                        reason = "verified_first_scan" if hint else "verified"
                else:
                    target = None
                    if len(candidates) > 1:
                        reason = "ambiguous_metadata"
                cache[key] = (target, reason, selected_mz)
            target, reason, selected_mz = cache[key]
            mapping.append({"original_id": str(original), "native_id": target, "reason": reason,
                            "rt_seconds": rt if math.isfinite(rt) else None, "precursor_mz": mz, "charge": charge})
            if hint:
                mapping[-1].update(file_id=hint[0], first_scan=hint[1], mzml_precursor_mz=selected_mz,
                                   abs_mz_difference_ppm=abs(mz-selected_mz)/mz*1e6 if mz and selected_mz else None)
        source_ids = {}
        for item in mapping:
            if item["native_id"] is not None:
                source_ids.setdefault(item["native_id"], set()).add(item["original_id"])
        collisions = {native for native, originals in source_ids.items() if len(originals) > 1}
        for item in mapping:
            if item["native_id"] in collisions:
                item.update(native_id=None, reason="multiple_source_ids_for_native_spectrum")
        matched = sum(item["native_id"] is not None for item in mapping)
        converted = sum(item["native_id"] is not None and item["native_id"] != item["original_id"] for item in mapping)
        reasons = Counter(item["reason"] for item in mapping)
        ambiguous = reasons["ambiguous_metadata"] + reasons["multiple_source_ids_for_native_spectrum"]
        examples = [{"spectrum_id": item["original_id"], "reason": item["reason"]}
                    for item in mapping if item["native_id"] is None][:5]
        result.loc[group.index, "spectrumID"] = [item["native_id"] or item["original_id"] for item in mapping]
        audits.append({"run": str(run), "plugin_rows": len(group),
                       "native_ms2_spectra": len(metadata), "matched_rows": matched,
                       "converted_rows": converted, "unmatched_rows": len(group)-matched,
                       "ambiguous_rows": ambiguous, "reason_counts": dict(reasons),
                       "rt_tolerance_seconds": rt_tolerance_seconds, "mz_tolerance_ppm": mz_tolerance_ppm,
                       "unmatched_examples": examples, "mapping": mapping})
    return result, audits


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
