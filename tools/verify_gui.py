"""Exercise the actual desktop application with a report, optionally leaving it open for review."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source", default="FragPipe")
    parser.add_argument("--close", action="store_true")
    args = parser.parse_args()
    output = ROOT / "build" / "gui_validation" / str(time.time_ns())
    output.mkdir(parents=True)
    os.environ["PROTEOMICSQC_SETTINGS"] = str(output / "settings.json")
    from proteomicsqc.gui import MSQCApp
    app = MSQCApp()
    app.source_var.set(args.source)
    app.input_var.set(str(args.input.resolve()))
    app.output_var.set(str(output))
    app.report_name_var.set("HeLa_2026_11_10")
    app.after(600, app.run_qc)
    started = time.monotonic()
    def completed():
        if not app.busy and (app.result_dir or time.monotonic() - started > 180):
            data = {"status": app.job_var.get(), "summary": app.summary_var.get(), "output": str(app.result_dir),
                    "html_exists": bool(app.report_file), "summary_rows": len(app.tables["Summary"].get_children()),
                    "by_run_preview_rows": len(app.run_preview.get_children())}
            (output / "gui_verification.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(json.dumps(data), flush=True)
            if args.close:
                app.destroy()
            return
        app.after(250, completed)
    app.after(1000, completed)
    app.mainloop()


if __name__ == "__main__":
    main()
