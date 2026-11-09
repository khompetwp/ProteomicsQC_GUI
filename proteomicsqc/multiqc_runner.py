"""PMultiQC worker with narrowly scoped 0.0.48 dtype compatibility fixes.

No package files or input files are changed. These conversions prevent plugin
errors on dictionary-encoded DIA-NN Run labels and numeric MaxQuant group IDs;
they do not alter the plugin's filters or scientific calculations.
"""
from importlib.metadata import version
import runpy
import sys


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
    sys.argv[0] = "multiqc"
    runpy.run_module("multiqc", run_name="__main__")


if __name__ == "__main__":
    main()
