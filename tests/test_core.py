import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from proteomicsqc import adapters
from proteomicsqc.engine import run_analysis
from proteomicsqc.gui import MSQCApp
from proteomicsqc.reporting import validate_report
from proteomicsqc.runtime import Cancelled
from proteomicsqc.tables import save_workbook
from proteomicsqc.outputs import create_run_directory, validate_report_name

FIXTURES = ROOT / "sample_data" / "synthetic_qc"


def history(directory):
    frame = pd.read_excel(directory / "QC_summary.xlsx", sheet_name="Run info", keep_default_na=False)
    return dict(zip(frame.setting, frame.value))


class CoreTests(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT / "build" / "test_runs"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temporary_root)
        self.root = Path(self.temp.name)
        self.psm = self.root / "psm.tsv"
        pd.DataFrame({"Peptide": ["NA", " PEP ", "PEP", ""], "Charge": ["2", "3", "bad", "inf"],
                      "Spectrum File": ["one", "one", "two", "two"],
                      "Calibrated Observed M/Z": [500.001, 499.999, -1, 0],
                      "Calculated M/Z": [500, 500, 500, 0]}).to_csv(self.psm, sep="\t", index=False)

    def tearDown(self):
        self.temp.cleanup()

    def analyze(self, source, data_source="FragPipe", level="PSM", html=False, directory="output"):
        outdir = self.root / directory
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = run_analysis(source, outdir, level, html, self.root, data_source)
        return code, outdir

    def test_fragpipe_regression_and_numeric_validity(self):
        before = self.psm.read_bytes()
        code, outdir = self.analyze(self.psm)
        self.assertEqual(code, 0)
        summary = pd.read_excel(outdir / "QC_summary.xlsx", sheet_name="Summary").iloc[0]
        self.assertEqual(summary.psms, 4)
        self.assertEqual(summary.unique_peptide_sequences, 2)
        self.assertEqual(summary.missing_peptide_rows, 1)
        self.assertEqual(summary.median_charge, 2.5)
        self.assertEqual(summary.mass_error_valid_rows, 2)
        self.assertAlmostEqual(summary.median_absolute_mass_error_ppm, 2)
        self.assertEqual([path.name for path in outdir.iterdir()], ["QC_summary.xlsx"])
        self.assertEqual(before, self.psm.read_bytes())

    def test_fragpipe_matches_original_code(self):
        path = ROOT / "tools" / "baseline_fragpipe_0_2.py"
        spec = importlib.util.spec_from_file_location("baseline", path)
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        with contextlib.redirect_stdout(io.StringIO()):
            expected, _, _ = baseline.summarize_psm(self.psm)
        code, outdir = self.analyze(self.psm)
        actual = pd.read_excel(outdir / "QC_summary.xlsx", sheet_name="Summary").iloc[0]
        for key, value in expected.items():
            if isinstance(value, (float, int)):
                self.assertAlmostEqual(float(actual[key]), value)
        self.assertEqual(code, 0)

    def test_custom_psm_filename_and_folder_discovery(self):
        custom = self.root / "HeLa รอบสอง.tsv"
        custom.write_bytes(self.psm.read_bytes())
        code, outdir = self.analyze(custom)
        self.assertEqual(code, 0)
        frame = pd.read_excel(outdir / "QC_summary.xlsx", sheet_name="Summary")
        self.assertEqual(frame.iloc[0].psms, 4)
        self.assertEqual(Path(frame.iloc[0].source_file), custom)
        variant = self.root / "psm_2.tsv"
        variant.write_bytes(self.psm.read_bytes())
        self.assertEqual(set(adapters.locate_inputs(self.root, "FragPipe", "PSM")), {self.psm, variant})

    def test_named_output_unicode_collision_and_invalid_paths(self):
        named = create_run_directory(self.root, "HeLa QC รอบสอง")
        self.assertEqual(named, self.root / "HeLa QC รอบสอง")
        marker = named / "keep.txt"
        marker.write_text("existing results")
        with self.assertRaises(ValueError):
            create_run_directory(self.root, named.name)
        self.assertEqual(marker.read_text(), "existing results")
        for name in ("../escape", "C:\\escape", "..", "CON", "NUL.txt", "run.", " run", "run ", "a/b", "a?b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_report_name(name)

    def test_gui_custom_input_named_folder_and_existing_result(self):
        app = MSQCApp()
        app.withdraw()
        custom = self.root / "psm_2.tsv"
        custom.write_bytes(self.psm.read_bytes())
        try:
            app.input_var.set(str(custom))
            app.output_var.set(str(self.root / "GUI"))
            app.report_name_var.set("HeLa รอบสอง")
            with patch("proteomicsqc.gui.messagebox.showerror") as error, patch("proteomicsqc.gui.messagebox.showwarning") as warning:
                app.run_qc()
                deadline = time.monotonic() + 30
                while app.busy and time.monotonic() < deadline:
                    app.update()
                    time.sleep(0.02)
                self.assertFalse(app.busy)
                error.assert_not_called()
                warning.assert_not_called()
                self.assertEqual(app.result_dir, self.root / "GUI" / "HeLa รอบสอง")
                self.assertEqual(history(app.result_dir)["status"], "complete")
                before = (app.result_dir / "QC_summary.xlsx").read_bytes()
                app.run_qc()
                warning.assert_called_once()
                self.assertFalse(app.busy)
                self.assertEqual(before, (app.result_dir / "QC_summary.xlsx").read_bytes())
        finally:
            app.destroy()

    def test_peptide_and_protein_literal_na(self):
        for level, column, label in (("Peptide", "Peptide", "unique_peptides"), ("Protein", "Protein", "unique_protein_identifiers")):
            path = self.root / (level + ".tsv")
            pd.DataFrame({column: ["NA", " PEP ", "PEP", ""], "other": [1, 2, 3, 4]}).to_csv(path, sep="\t", index=False)
            code, outdir = self.analyze(path, level=level, directory=level)
            self.assertEqual(code, 0)
            summary = pd.read_excel(outdir / "QC_summary.xlsx", sheet_name="Summary").iloc[0]
            self.assertEqual(summary[label], 2)
            self.assertEqual(summary.rows, 4)

    def test_diann_counts_retain_decoys_high_q_missing_values(self):
        source = FIXTURES / "diann_2_2_0" / "report.parquet"
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        code, outdir = self.analyze(source, "DIA-NN", "Precursor")
        self.assertEqual(code, 0)
        summary = pd.read_excel(outdir / "QC_summary.xlsx", sheet_name="Summary").iloc[0]
        self.assertEqual(summary.input_rows, 678)
        self.assertEqual(summary.decoy_flagged_rows_retained, 54)
        self.assertEqual(summary.rows_q_value_above_0_01_retained, 33)
        self.assertEqual(summary.unique_precursors, 120)
        runs = pd.read_excel(outdir / "QC_summary.xlsx", sheet_name="By run")
        self.assertEqual(len(runs), 6)
        self.assertEqual(runs.input_rows.sum(), 678)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)

    def test_diann_tsv_and_parquet_have_identical_counts(self):
        source = FIXTURES / "diann_2_2_0" / "report.parquet"
        frame = pd.read_parquet(source)
        frame.to_csv(self.root / "report.tsv", sep="\t", index=False)
        code, outdir = self.analyze(self.root / "report.tsv", "DIA-NN", "Precursor")
        self.assertEqual(code, 0)
        summary = pd.read_excel(outdir / "QC_summary.xlsx", sheet_name="Summary").iloc[0]
        self.assertEqual(summary.input_rows, 678)
        self.assertEqual(summary.unique_precursors, 120)

    def test_diann_ambiguous_folder_is_rejected(self):
        for folder in (self.root / "a", self.root / "b"):
            folder.mkdir()
            (folder / "report.parquet").touch()
        with self.assertRaises(ValueError):
            adapters.locate_inputs(self.root, "DIA-NN", "Precursor")

    def test_maxquant_counting_units_and_no_filtering(self):
        code, outdir = self.analyze(FIXTURES / "maxquant_unspecified", "MaxQuant", "Evidence")
        self.assertEqual(code, 0)
        frame = pd.read_excel(outdir / "QC_summary.xlsx", sheet_name="By run")
        self.assertEqual(frame.evidence_rows.sum(), 678)
        self.assertEqual(frame.psm_rows.sum(), 618)
        self.assertEqual(frame.mbr_evidence_rows.sum(), 60)
        self.assertEqual(frame.reverse_flagged_rows_retained.sum(), 54)
        self.assertEqual(frame.contaminant_flagged_rows_retained.sum(), 59)
        self.assertIn("not inferred", history(outdir)["mbr_note"])

    def test_invalid_schema_saved_as_failure(self):
        self.psm.write_text("Peptide\nPEP\n", encoding="utf-8")
        code, outdir = self.analyze(self.psm)
        self.assertEqual(code, 2)
        self.assertEqual(history(outdir)["status"], "failed")
        self.assertTrue((outdir / "processing.log").exists())

    def test_cancel_before_work_and_during_report(self):
        outdir = self.root / "cancel"
        outdir.mkdir()
        (outdir / ".cancel_requested").touch()
        code, outdir = self.analyze(self.psm, directory="cancel")
        self.assertEqual(code, 130)
        self.assertEqual(history(outdir)["status"], "cancelled")
        with patch("proteomicsqc.engine.run_pmultiqc", side_effect=Cancelled("cancelled in report")):
            code, outdir = self.analyze(self.psm, html=True, directory="cancel_report")
        self.assertEqual(code, 130)
        self.assertEqual(history(outdir)["status"], "cancelled")

    def test_html_failure_retains_excel(self):
        with patch("proteomicsqc.engine.run_pmultiqc", side_effect=RuntimeError("parser failed")):
            code, outdir = self.analyze(self.psm, html=True)
        self.assertEqual(code, 1)
        self.assertEqual(history(outdir)["status"], "partial")
        self.assertFalse(pd.read_excel(outdir / "QC_summary.xlsx", sheet_name="Summary").empty)

    def test_empty_or_partially_parsed_html_is_rejected(self):
        (self.root / "_support").mkdir()
        (self.root / "multiqc_report.html").write_text("<html>empty</html>")
        state = self.root / "_support" / "multiqc_data.json"
        state.write_text(json.dumps({"report_plot_data": {}}))
        with self.assertRaises(RuntimeError):
            validate_report(self.root, [], {})
        state.write_text(json.dumps({"report_plot_data": {"plot": {}}}))
        with self.assertRaises(RuntimeError):
            validate_report(self.root, ["plugin encountered an error and was skipped"], {})

    def test_excel_preserves_text_that_looks_like_formula(self):
        save_workbook(self.root, {"Summary": pd.DataFrame({"value": ["=1+1", "00123", "NA"]})}, {"status": "complete"})
        import openpyxl
        book = openpyxl.load_workbook(self.root / "QC_summary.xlsx", data_only=False)
        self.assertEqual(book["Summary"]["A2"].data_type, "s")
        self.assertEqual(book["Summary"]["A3"].value, "00123")
        book.close()

    def test_gui_sources_preview_and_cooperative_cancel(self):
        app = MSQCApp()
        app.withdraw()
        try:
            for source, level in (("DIA-NN", "Precursor"), ("MaxQuant", "Evidence"), ("FragPipe", "PSM")):
                app.source_var.set(source)
                self.assertEqual(app.level_var.get(), level)
            app.input_var.set(str(self.psm))
            app.output_var.set(str(self.root / "GUI"))
            app.run_qc()
            app.cancel_qc()
            deadline = time.monotonic() + 30
            with patch("proteomicsqc.gui.messagebox.showerror") as error:
                while app.busy and time.monotonic() < deadline:
                    app.update()
                    time.sleep(0.02)
                self.assertFalse(app.busy)
                error.assert_not_called()
            self.assertEqual(history(app.result_dir)["status"], "cancelled")
            self.assertIn("cancelled", app.summary_var.get())
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
