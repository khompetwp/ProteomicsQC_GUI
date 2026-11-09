"""Cooperative job cancellation shared by the engine and report subprocess."""
from pathlib import Path


class Cancelled(Exception):
    pass


def cancellation_check(outdir: Path):
    def check():
        if (outdir / ".cancel_requested").exists():
            raise Cancelled("Cancelled by the user. Data already read was not treated as a complete analysis.")
    return check
