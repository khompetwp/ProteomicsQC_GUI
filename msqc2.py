"""Compatibility entry point for the ProteomicsQC command-line interface."""
from proteomicsqc.cli import main
from proteomicsqc.engine import run_analysis
from proteomicsqc.fragpipe import summarize_psm, summarize_frame, locate_psm_files

if __name__ == "__main__":
    import sys
    sys.exit(main())
