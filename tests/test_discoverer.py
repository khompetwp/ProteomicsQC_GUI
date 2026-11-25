"""PD counting semantics and file selection regressions (no spectrum RAM load)."""
import copy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from xml.sax import SAXParseException
import pandas as pd

from proteomicsqc import adapters, discoverer
from proteomicsqc.preflight import check_input

FIXTURE = Path(__file__).resolve().parents[1] / "sample_data/synthetic_qc/proteome_discoverer/SYNTHETIC_PD_like.mzid"
NS = {"m": "http://psidev.info/psi/pi/mzIdentML/1.1"}


class DiscovererTests(unittest.TestCase):
    def test_explicit_pd_first_scan_verifies_shifted_precursor(self):
        xml = """<MzIdentML><AnalysisSoftware name="Proteome Discoverer"/>
        <!--FileId=1 (F1); FirstScan=2087; SpectrumId=486-->
        <SpectrumIdentificationResult spectrumID="scan=486" spectraData_ref="raw1">
        <cvParam accession="MS:1000894" value="10"/></SpectrumIdentificationResult></MzIdentML>"""
        hints = {}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pd.mzid"
            path.write_text(xml, encoding="utf-8")
            times, _ = discoverer.pd_retention_times(path, first_scans=hints)
        frame = pd.DataFrame([dict(filename="run", spectrumID="scan=486", pd_rt_seconds=times["scan=486"],
                                   experimentalMassToCharge=544.29, chargeState=2)])
        spectrum = dict(native_id="controllerType=0 controllerNumber=1 scan=2087", rt_seconds=600,
                        precursor_mz=544.27, charge=2)
        for charge, expected in ((2, spectrum["native_id"]), (3, None)):
            _, audits = discoverer.align_spectrum_ids(frame, {"run": [dict(spectrum, charge=charge)]},
                                                      first_scans_by_run={"run": hints})
            match = audits[0]["mapping"][0]
            self.assertEqual(match["native_id"], expected)
            self.assertGreater(match["abs_mz_difference_ppm"], 10)

    def test_html_native_ids_and_unmatched_failure_keep_inputs_and_excel(self):
        import pyopenms as oms
        from proteomicsqc.engine import run_analysis
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inputs = root / "inputs"
            inputs.mkdir()
            mzid = inputs / FIXTURE.name
            mzid.write_bytes(FIXTURE.read_bytes())
            mzml = mzid.with_suffix(".mzML")
            experiment = oms.MSExperiment()
            oms.MzMLFile().load(str(FIXTURE.with_suffix(".mzML")), experiment)
            for i in range(experiment.size()):
                spectrum = experiment[i]
                number = int(spectrum.getNativeID().split("=")[-1]) + 1000
                spectrum.setNativeID(f"controllerType=0 controllerNumber=1 scan={number}")
                experiment[i] = spectrum
            oms.MzMLFile().store(str(mzml), experiment)
            before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (mzid, mzml)]
            out = root / "matched"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = run_analysis(mzid, out, "Identification", True, root, discoverer.SOURCE)
            self.assertEqual(code, 0, (out / "processing.log").read_text() if (out / "processing.log").exists() else "")
            audit = json.loads((out / "_support/pd_id_matching.json").read_text())
            self.assertEqual(audit["runs"][0]["converted_rows"], 24)
            self.assertEqual(audit["runs"][0]["unmatched_rows"], 0)
            plots = json.loads((out / "_support/multiqc_data.json").read_text())["report_plot_data"]
            self.assertTrue(plots)
            self.assertEqual(before, [hashlib.sha256(p.read_bytes()).hexdigest() for p in (mzid, mzml)])
            tree = ET.parse(mzid)
            tree.find(".//m:SpectrumIdentificationItem", NS).set("experimentalMassToCharge", "9999999")
            tree.write(mzid, encoding="utf-8", xml_declaration=True)
            out = root / "unmatched"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = run_analysis(mzid, out, "Identification", True, root, discoverer.SOURCE)
            self.assertEqual(code, 1)
            self.assertEqual(pd.read_excel(out / "QC_summary.xlsx", sheet_name="Summary").iloc[0].psm_items, 24)
            info = pd.read_excel(out / "QC_summary.xlsx", sheet_name="Run info").set_index("setting")["value"]
            self.assertEqual(info["status"], "partial")
            self.assertEqual(info["pd_id_unmatched_rows"], 1)
            self.assertIn("matching is incomplete", info["error"])

    def test_native_id_alignment_preserves_rows_and_separates_runs(self):
        native = "controllerType=0 controllerNumber=1 scan=63"
        frame = pd.DataFrame({"filename": ["A", "A", "B", "A"],
                              "spectrumID": ["scan=63", "scan=63", "scan=63", "index=99"],
                              "pd_rt_seconds": [10., 10., 20., 40.],
                              "experimentalMassToCharge": [500., 500., 600., 700.],
                              "chargeState": [2, 2, 3, 2],
                              "score": [1, 2, 3, 4]})
        original = frame.copy(deep=True)
        aligned, audit = discoverer.align_spectrum_ids(frame, {
            "A": [{"native_id": native, "rt_seconds": 10., "precursor_mz": 500., "charge": 2}],
            "B": [{"native_id": "scan=63", "rt_seconds": 20., "precursor_mz": 600., "charge": 3}]})
        self.assertEqual(aligned.spectrumID.tolist(), [native, native, "scan=63", "index=99"])
        self.assertEqual(aligned.score.tolist(), [1, 2, 3, 4])
        self.assertEqual(audit[0]["matched_rows"], 2)
        self.assertEqual(audit[0]["converted_rows"], 2)
        self.assertEqual(audit[0]["unmatched_rows"], 1)
        self.assertEqual(audit[1]["converted_rows"], 0)
        pd.testing.assert_frame_equal(frame, original)

    def test_id_collision_and_missing_run_do_not_guess(self):
        frame = pd.DataFrame({"filename": ["A"], "spectrumID": ["scan=63"],
                              "pd_rt_seconds": [10.], "experimentalMassToCharge": [500.], "chargeState": [2]})
        record = {"native_id": "scan=63", "rt_seconds": 10., "precursor_mz": 500., "charge": 2}
        with self.assertRaisesRegex(ValueError, "duplicate"):
            discoverer.align_spectrum_ids(frame, {"A": [record, record]})
        _, audit = discoverer.align_spectrum_ids(frame, {"A": [record, {**record, "native_id": "scan=64"}]})
        self.assertEqual(audit[0]["ambiguous_rows"], 1)
        _, audit = discoverer.align_spectrum_ids(frame, {"B": [record]})
        self.assertEqual(audit[0]["matched_rows"], 0)
        self.assertEqual(audit[0]["unmatched_rows"], 1)
        self.assertIsNone(discoverer.scan_number("index=63"))
        self.assertIsNone(discoverer.scan_number("unrecognized scan=63"))
        frame["spectrumID"] = "controllerType=0 controllerNumber=2 scan=63"
        _, audit = discoverer.align_spectrum_ids(frame, {"A": [{**record, "native_id": "controllerType=0 controllerNumber=1 scan=63"}]})
        self.assertEqual(audit[0]["unmatched_rows"], 1)

    def test_same_scan_number_is_not_evidence_and_renumbered_metadata_is(self):
        frame = pd.DataFrame({"filename": ["A"], "spectrumID": ["scan=63"],
                              "pd_rt_seconds": [10.], "experimentalMassToCharge": [500.], "chargeState": [2]})
        wrong = {"native_id": "scan=63", "rt_seconds": 20., "precursor_mz": 600., "charge": 3}
        aligned, audits = discoverer.align_spectrum_ids(frame, {"A": [wrong]})
        self.assertEqual(audits[0]["matched_rows"], 0)
        right = {"native_id": "scan=1587", "rt_seconds": 10., "precursor_mz": 500.001, "charge": 2}
        aligned, audits = discoverer.align_spectrum_ids(frame, {"A": [wrong, right]})
        self.assertEqual(aligned.iloc[0].spectrumID, "scan=1587")
        self.assertEqual(audits[0]["converted_rows"], 1)
        for changed in ({"charge": 3}, {"precursor_mz": 501.}, {"rt_seconds": None}):
            _, audits = discoverer.align_spectrum_ids(frame, {"A": [{**right, **changed}]})
            self.assertEqual(audits[0]["matched_rows"], 0)

    def test_two_source_ids_cannot_silently_collapse_to_one_native_id(self):
        frame = pd.DataFrame({"filename": ["A", "A"], "spectrumID": ["scan=1", "scan=2"],
                              "pd_rt_seconds": [10., 10.], "experimentalMassToCharge": [500., 500.], "chargeState": [2, 2]})
        record = {"native_id": "scan=1587", "rt_seconds": 10., "precursor_mz": 500., "charge": 2}
        aligned, audits = discoverer.align_spectrum_ids(frame, {"A": [record]})
        self.assertEqual(audits[0]["matched_rows"], 0)
        self.assertEqual(audits[0]["ambiguous_rows"], 2)

    def test_retention_time_units_and_pd_only_unitless_policy(self):
        xml = '''<MzIdentML xmlns="http://psidev.info/psi/pi/mzIdentML/1.1">
        <AnalysisSoftwareList><AnalysisSoftware id="Proteome Discoverer"/></AnalysisSoftwareList>
        <SpectrumIdentificationResult spectrumID="scan=1"><cvParam accession="MS:1000894" value="2"/></SpectrumIdentificationResult>
        <SpectrumIdentificationResult spectrumID="scan=2"><cvParam accession="MS:1000894" value="2" unitAccession="UO:0000010"/></SpectrumIdentificationResult>
        <SpectrumIdentificationResult spectrumID="scan=3"><cvParam accession="MS:1000894" value="2" unitAccession="UO:0000031"/></SpectrumIdentificationResult>
        </MzIdentML>'''
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rt.mzid"
            path.write_text(xml, encoding="utf-8")
            rt, policy = discoverer.pd_retention_times(path)
            self.assertEqual(rt, {"scan=1": 120., "scan=2": 2., "scan=3": 120.})
            self.assertEqual(policy["unitless_spectrum_ids"], 1)
            path.write_text(xml.replace("Proteome Discoverer", "Other engine"), encoding="utf-8")
            rt, _ = discoverer.pd_retention_times(path)
            self.assertIsNone(rt["scan=1"])

    def test_metadata_reader_selects_ms2_without_decoding_binary(self):
        xml = '''<mzML xmlns="http://psi.hupo.org/ms/mzml"><run><spectrumList count="2">
        <spectrum id="scan=1"><cvParam accession="MS:1000511" value="1"/></spectrum>
        <spectrum id="controllerType=0 controllerNumber=1 scan=2">
        <cvParam accession="MS:1000511" value="2"/>
        <binaryDataArrayList><binaryDataArray><binary>NOT_BASE64</binary></binaryDataArray></binaryDataArrayList>
        </spectrum></spectrumList></run></mzML>'''
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "metadata.mzML"
            path.write_text(xml, encoding="utf-8")
            self.assertEqual(discoverer.mzml_ms2_ids(path), ["controllerType=0 controllerNumber=1 scan=2"])
            path.write_text(xml[:-8], encoding="utf-8")
            with self.assertRaises(SAXParseException):
                discoverer.mzml_ms2_ids(path)

    def test_paired_fixture_counts_and_selection(self):
        files, warnings = check_input(FIXTURE, discoverer.SOURCE, "Identification", html=True)
        self.assertEqual(files, [FIXTURE])
        selected = discoverer.report_inputs(files)
        self.assertEqual(set(selected), {FIXTURE, FIXTURE.with_suffix(".mzML")})
        summary, runs, audit, missing = discoverer.analyze(files, lambda: None)
        self.assertEqual(summary[0]["psm_items"], 24)
        self.assertEqual(summary[0]["rank1_passing_items"], 24)
        self.assertEqual(summary[0]["unique_peptide_sequences"], 6)
        self.assertEqual(summary[0]["referenced_protein_accessions"], 3)
        self.assertEqual(runs[0]["run"], FIXTURE.with_suffix(".mzML").name)

    def test_alternative_ranks_failed_thresholds_and_decoys_are_retained(self):
        tree = ET.parse(FIXTURE)
        sir = tree.find(".//m:SpectrumIdentificationResult", NS)
        original = sir.find("m:SpectrumIdentificationItem", NS)
        for rank, passed in ((2, "true"), (1, "false")):
            clone = copy.deepcopy(original)
            clone.set("id", "ADDED_" + str(rank))
            clone.set("rank", str(rank))
            clone.set("passThreshold", passed)
            sir.insert(1, clone)
        tree.find(".//m:PeptideEvidence", NS).set("isDecoy", "true")
        rt = sir.find("m:cvParam", NS)
        rt.attrib.pop("unitAccession")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.mzid"
            tree.write(path, encoding="utf-8", xml_declaration=True)
            frame, _ = discoverer.read_items(path, lambda: None)
            counts = discoverer.counts(frame)
            self.assertEqual(counts["psm_items"], 26)
            self.assertEqual(counts["rank1_passing_items"], 24)
            self.assertEqual(counts["pass_threshold_false_items_retained"], 1)
            self.assertEqual(counts["any_decoy_evidence_items_retained"], 6)
            self.assertEqual(counts["rt_items_with_unspecified_unit"], 3)
            self.assertTrue(frame.loc[frame.spectrum_id.eq("scan=2"), "rt_seconds"].isna().all())
            self.assertEqual(adapters.locate_inputs(path, discoverer.SOURCE, "Identification"), [path])
            self.assertTrue(any("no same-name" in w for w in discoverer.preflight([path], True)))
            with self.assertRaisesRegex(ValueError, "HTML requires"):
                discoverer.report_inputs([path])

    def test_broken_reference_and_truncated_xml_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.mzid"
            tree = ET.parse(FIXTURE)
            tree.find(".//m:SpectrumIdentificationItem", NS).set("peptide_ref", "MISSING")
            tree.write(path)
            with self.assertRaisesRegex(ValueError, "unresolved peptide"):
                discoverer.read_items(path, lambda: None)
            path.write_text("<MzIdentML><broken>", encoding="utf-8")
            with self.assertRaises(ET.ParseError):
                discoverer.read_items(path, lambda: None)


if __name__ == "__main__":
    unittest.main()
