"""PMultiQC worker with narrowly scoped 0.0.48 compatibility fixes.

No package files or input files are changed. These conversions prevent plugin
errors on dictionary-encoded DIA-NN Run labels and numeric MaxQuant group IDs;
PD mzIdentML scan-only IDs are aligned with native mzML MS2 IDs in memory.
These adapters do not alter the plugin's filters or score calculations.
"""
from importlib.metadata import version
import json
import os
import runpy
import sys
from pathlib import Path


def install_pd_id_alignment():
    """Adapt only the selected PD mzML pairs, inside this subprocess."""
    selected = os.environ.get("PROTEOMICSQC_PD_PAIRS")
    if not selected:
        return
    # Running a script by path places proteomicsqc/, not its parent, on sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from proteomicsqc.discoverer import mzml_ms2_metadata, pd_retention_times, align_spectrum_ids
    from pmultiqc.modules.common.ms.mzid import MzidReader
    from pmultiqc.modules.common.file_utils import file_prefix

    audit_path = Path(os.environ["PROTEOMICSQC_PD_AUDIT"])
    state = {"status": "pending", "runs": [],
             "matching_method": "PD FirstScan + RT + charge, or unique same-run RT + precursor m/z + charge when FirstScan is absent",
             "counting_unit": "PMultiQC reader rows after its existing filters, including protein-evidence expansion; not Excel item counts"}

    def save():
        audit_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    if version("pmultiqc") != "0.0.48":
        state.update(status="failed", error="PD spectrum ID compatibility is tested only with PMultiQC 0.0.48.")
        save()
        raise RuntimeError(state["error"])
    original_parse = MzidReader.parse

    def parse(self, **kwargs):
        try:
            original_parse(self, **kwargs)
            frame = self.filtered_mzid_df
            if frame.empty:
                raise ValueError("PMultiQC found no usable mzIdentML identification rows.")
            ids = {}
            retention_times = {}
            first_scans = {}
            policies = {}
            for pair in json.loads(selected):
                spectrum = Path(pair["spectrum"])
                # MGF keeps the upstream reader unchanged; this fix targets mzML.
                if spectrum.suffix.lower() != ".mzml":
                    continue
                run = file_prefix(str(spectrum))
                print(f"PD ID matching: streaming MS2 RT/mz/charge metadata for {run}...", flush=True)
                ids[run] = mzml_ms2_metadata(spectrum)
                first_scans[run] = {}
                retention_times[run], policies[run] = pd_retention_times(Path(pair["mzid"]), first_scans=first_scans[run])
                print("PD RT policy: " + json.dumps({"run": run, **policies[run]}), flush=True)
            frame = frame.copy()
            frame["pd_rt_seconds"] = [retention_times.get(run, {}).get(spectrum_id)
                                      for run, spectrum_id in zip(frame.filename, frame.spectrumID)]
            mzml_rows = frame[frame.filename.isin(ids)]
            expected_runs = {file_prefix(pair["mzid"]) for pair in json.loads(selected)
                             if Path(pair["spectrum"]).suffix.lower() == ".mzml"}
            missing_runs = expected_runs - set(mzml_rows.filename)
            if missing_runs:
                raise ValueError("PD identification run names do not match spectrum files: " + ", ".join(sorted(missing_runs)))
            all_runs = {file_prefix(pair["mzid"]) for pair in json.loads(selected)}
            if set(frame.filename) - all_runs:
                raise ValueError("mzIdentML contains run names outside the selected spectrum pairs.")
            aligned, audits = align_spectrum_ids(mzml_rows, ids, first_scans_by_run=first_scans)
            for audit in audits:
                audit.update(policies[audit["run"]])
            state["runs"] = audits
            for audit in audits:
                print("PD ID matching: " + json.dumps({k: v for k, v in audit.items() if k != "mapping"}), flush=True)
            if any(audit["unmatched_rows"] for audit in audits):
                total = sum(audit["plugin_rows"] for audit in audits)
                matched = sum(audit["matched_rows"] for audit in audits)
                ambiguous = sum(audit["ambiguous_rows"] for audit in audits)
                raise ValueError(f"PD spectrum metadata matching is incomplete: {matched}/{total} rows verified, {total-matched} unresolved ({ambiguous} ambiguous). HTML stopped to avoid reporting a matched subset. See pd_id_matching.json; Excel QC is retained.")
            frame.loc[aligned.index, "spectrumID"] = aligned["spectrumID"]
            self.filtered_mzid_df = frame.drop(columns=["pd_rt_seconds"])
            state["status"] = "complete"
            save()
        except Exception as exc:
            state.update(status="failed", error=str(exc))
            save()
            import traceback
            traceback.print_exc()
            raise

    MzidReader.parse = parse
    # The upstream module swallows exceptions and logs only their short text.
    # Keep a full traceback and identify missing prerequisites before plotting.
    from pmultiqc.modules.mzidentml.mzidentml import MzIdentMLModule
    original_draw = MzIdentMLModule.draw_plots

    def draw(self):
        try:
            if any(Path(pair["spectrum"]).suffix.lower() == ".mzml" for pair in json.loads(selected)):
                required = ("missed_clevages_heatmap_score", "missed_cleavages_var_score",
                            "id_rt_score", "heatmap_over_sampling_score", "heatmap_pep_missing_score")
                for run in self.ms_with_psm:
                    missing = [name for name in required if run not in getattr(self, name, {})]
                    if missing:
                        raise ValueError(f"{run}: missing graph inputs: {', '.join(missing)}. Check spectrum matching and processing.log.")
            return original_draw(self)
        except Exception:
            import traceback
            traceback.print_exc()
            raise

    MzIdentMLModule.draw_plots = draw


def install_fragpipe_selection():
    selected = os.environ.get("PROTEOMICSQC_PSM_INPUTS")
    if selected is None:
        return
    from pathlib import Path
    paths = json.loads(selected)
    if not paths or not all(Path(path).is_file() for path in paths):
        raise ValueError("Selected FragPipe PSM files are unavailable.")
    from pmultiqc.modules.fragpipe import fragpipe
    original = fragpipe.get_fragpipe_files

    def get_files(find_log_files):
        files = original(find_log_files) or {}
        files["psm"] = paths
        return files

    fragpipe.get_fragpipe_files = get_files


def install_compatibility():
    if version("pmultiqc") != "0.0.48":
        return
    from pmultiqc.modules.common.ms.diann import DiannReader, DIANN_REPORT_STRING_COLUMNS
    original_parse = DiannReader.parse

    def parse(self, **kwargs):
        result = original_parse(self, **kwargs)
        for column in DIANN_REPORT_STRING_COLUMNS:
            if column in self.report_data:
                self.report_data[column] = self.report_data[column].astype("string")
        return result

    DiannReader.parse = parse
    from pmultiqc.modules.maxquant import maxquant_utils
    original_read = maxquant_utils.read

    def read(*args, **kwargs):
        frame = original_read(*args, **kwargs)
        if "protein group ids" in frame:
            frame["protein group ids"] = frame["protein group ids"].astype("string")
        return frame

    maxquant_utils.read = read


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    install_compatibility()
    install_fragpipe_selection()
    install_pd_id_alignment()
    sys.argv[0] = "multiqc"
    runpy.run_module("multiqc", run_name="__main__")


if __name__ == "__main__":
    main()
