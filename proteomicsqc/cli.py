"""Command-line entry point shared by source and portable distributions."""
import argparse
from datetime import datetime
from pathlib import Path
import sys
import tempfile

from . import __version__, adapters
from .engine import run_analysis


def main(argv=None):
    parser = argparse.ArgumentParser(description="ProteomicsQC: FragPipe, DIA-NN and MaxQuant table QC")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path.cwd() / "results")
    parser.add_argument("--source", choices=adapters.SOURCES, default="FragPipe")
    parser.add_argument("--level", default=None)
    parser.add_argument("--run-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--skip-multiqc", action="store_true")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        import openpyxl
        root = args.output.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        run_dir = args.run_dir.expanduser().resolve() if args.run_dir else Path(tempfile.mkdtemp(prefix=datetime.now().strftime("qc_%Y%m%d_%H%M%S_"), dir=root))
        level = args.level or adapters.LEVELS[args.source][0]
        html = not args.skip_multiqc and not (args.source == "FragPipe" and level != "PSM")
        return run_analysis(args.input.expanduser().resolve(), run_dir, level, html, root, args.source)
    except (OSError, ValueError, ImportError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2
