"""PD counting semantics and file selection regressions (no spectrum RAM load)."""
import copy
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from proteomicsqc import adapters, discoverer
from proteomicsqc.preflight import check_input

FIXTURE = Path(__file__).resolve().parents[1] / "sample_data/synthetic_qc/proteome_discoverer/SYNTHETIC_PD_like.mzid"
NS = {"m": "http://psidev.info/psi/pi/mzIdentML/1.1"}


class DiscovererTests(unittest.TestCase):
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
