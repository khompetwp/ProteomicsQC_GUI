"""Desktop FragPipe QC. Keep msqc2.py beside this file.

Install requirements.txt, then run python msqc_gui.py.
Each run saves QC_summary.xlsx and optional PMultiQC HTML.
"""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd

LEVELS = ("PSM", "Peptide", "Protein")


class MSQCApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FragPipe Quality Control")
        self.geometry("1100x760")
        self.minsize(820, 580)
        self.input_var = tk.StringVar()
        self.level_var = tk.StringVar(value="PSM")
        self.output_var = tk.StringVar()
        self.multiqc_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready — select a TSV file or a folder containing psm.tsv files")
        self.summary_var = tk.StringVar(value="Run QC to see results here.")
        self.scope_var = tk.StringVar()
        self.input_var.trace_add("write", self._scope_changed)
        self.level_var.trace_add("write", self._scope_changed)
        self.multiqc_var.trace_add("write", self._scope_changed)
        self.events = queue.Queue()
        self.busy = False
        self.result_dir = None
        self.report_file = None
        self.excel_file = None
        self.controls = []
        main = ttk.Frame(self, padding=18)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(8, weight=1)
        ttk.Label(main, text="FragPipe QC", font=("Segoe UI", 19, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 14))
        ttk.Label(main, text="Input file / folder").grid(row=1, column=0, sticky="w")
        entry = ttk.Entry(main, textvariable=self.input_var)
        entry.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        self.controls.append(entry)
        self._button(main, "File…", self.browse_input, 1, 2)
        self._button(main, "Folder…", self.browse_folder, 1, 3)
        ttk.Label(main, text="Data level").grid(row=2, column=0, sticky="w")
        self.level_box = ttk.Combobox(main, textvariable=self.level_var, values=LEVELS, state="readonly", width=18)
        self.level_box.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        self.level_box.bind("<<ComboboxSelected>>", self._level_changed)
        ttk.Label(main, text="Output folder").grid(row=3, column=0, sticky="w")
        entry = ttk.Entry(main, textvariable=self.output_var)
        entry.grid(row=3, column=1, sticky="ew", padx=10, pady=5)
        self.controls.append(entry)
        self._button(main, "Browse…", self.browse_output, 3, 2)
        self.multiqc_check = ttk.Checkbutton(main, text="Create PMultiQC HTML report (PSM only; requires pmultiqc)", variable=self.multiqc_var)
        self.multiqc_check.grid(row=4, column=1, columnspan=3, sticky="w", padx=10, pady=5)
        ttk.Label(main, textvariable=self.scope_var, wraplength=1000, foreground="#555555").grid(row=5, column=0, columnspan=4, sticky="w", pady=5)
        actions = ttk.Frame(main)
        actions.grid(row=6, column=0, columnspan=4, sticky="ew", pady=10)
        self.run_btn = ttk.Button(actions, text="Run QC", command=self.run_qc)
        self.run_btn.pack(side="left")
        self.controls.append(self.run_btn)
        self.open_btn = ttk.Button(actions, text="Open results folder", command=self.open_results, state="disabled")
        self.open_btn.pack(side="left", padx=8)
        self.excel_btn = ttk.Button(actions, text="Open Excel summary", command=self.open_excel, state="disabled")
        self.excel_btn.pack(side="left", padx=(0, 8))
        self.report_btn = ttk.Button(actions, text="Open HTML report", command=self.open_report, state="disabled")
        self.report_btn.pack(side="left")
        self.progress = ttk.Progressbar(actions, mode="indeterminate")
        self.progress.pack(side="right", fill="x", expand=True, padx=(20, 0))
        ttk.Label(main, textvariable=self.summary_var, wraplength=1000, font=("Segoe UI", 10, "bold")).grid(row=7, column=0, columnspan=4, sticky="w", pady=(0, 10))
        tabs = ttk.Notebook(main)
        tabs.grid(row=8, column=0, columnspan=4, sticky="nsew")
        self.tables = {}
        for name in ("Summary", "By run", "Numeric audit", "Missing values", "Input files", "Run info"):
            frame = ttk.Frame(tabs)
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            tree = ttk.Treeview(frame, show="headings")
            tree.grid(row=0, column=0, sticky="nsew")
            ys = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            xs = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
            ys.grid(row=0, column=1, sticky="ns")
            xs.grid(row=1, column=0, sticky="ew")
            tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
            tabs.add(frame, text=name)
            self.tables[name] = tree
        log_frame = ttk.Frame(tabs)
        self.log = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        self.log.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scroll.set)
        tabs.add(log_frame, text="Log")
        ttk.Label(main, textvariable=self.status_var, wraplength=1000).grid(row=9, column=0, columnspan=4, sticky="w", pady=(10, 0))
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._scope_changed()
        self.after(100, self._poll)

    def _scope_changed(self, *args):
        selected = self.input_var.get().strip().strip('"')
        note = "Output: QC_summary.xlsx; HTML optional; report support files stay in _support/."
        if self.level_var.get() == "PSM" and self.multiqc_var.get():
            if selected:
                path = Path(selected).expanduser()
                scan = path.parent if path.is_file() else path
                note += f"\nPMultiQC scans ALL original files in: {scan}. GUI QC counts psm.tsv files only."
            else:
                note += "\nPMultiQC scans the whole selected folder (or the selected file's parent)."
        else:
            note += "\nNo HTML requested. Input files are preserved; no QC filtering is applied."
        self.scope_var.set(note)

    def _button(self, parent, text, command, row, column):
        button = ttk.Button(parent, text=text, command=command)
        button.grid(row=row, column=column, padx=4)
        self.controls.append(button)

    def _level_changed(self, event=None):
        psm = self.level_var.get() == "PSM"
        if not psm:
            self.multiqc_var.set(False)
        self.multiqc_check.configure(state="normal" if psm and not self.busy else "disabled")

    def browse_input(self):
        selected = filedialog.askopenfilename(title="Select FragPipe TSV", filetypes=[("TSV files", "*.tsv")])
        if selected:
            self.input_var.set(selected)

    def browse_folder(self):
        selected = filedialog.askdirectory(title="Select folder containing psm.tsv files")
        if selected:
            self.input_var.set(selected)
            self.level_var.set("PSM")
            self._level_changed()

    def browse_output(self):
        selected = filedialog.askdirectory(title="Select output parent folder")
        if selected:
            self.output_var.set(selected)

    def run_qc(self):
        if self.busy:
            return
        try:
            selected = self.input_var.get().strip().strip('"')
            if not selected:
                raise ValueError("Please select an input file or folder.")
            source = Path(selected).expanduser().resolve()
            if not source.exists():
                raise ValueError("Input does not exist.")
            level = self.level_var.get()
            if level != "PSM" and (not source.is_file() or source.suffix.lower() != ".tsv"):
                raise ValueError("Peptide and Protein modes require a single TSV file.")
            if level == "PSM" and source.is_file() and source.name.lower() != "psm.tsv":
                raise ValueError("PSM mode uses msqc2.py and requires a file named psm.tsv.")
            if not Path(__file__).with_name("msqc2.py").is_file():
                raise ValueError("Place msqc2.py in the same folder as this GUI.")
            try:
                import openpyxl
            except ImportError:
                raise ValueError("Excel output requires openpyxl. Install requirements.txt in this Python environment.")
            output = self.output_var.get().strip().strip('"')
            root = Path(output).expanduser().resolve() if output else (source if source.is_dir() else source.parent) / "ResultQC"
        except (OSError, ValueError) as exc:
            messagebox.showwarning("Check input", str(exc))
            return
        self.busy = True
        for control in self.controls:
            control.configure(state="disabled")
        self.level_box.configure(state="disabled")
        self._level_changed()
        self.open_btn.configure(state="disabled")
        self.report_btn.configure(state="disabled")
        self.excel_btn.configure(state="disabled")
        self.result_dir = self.report_file = self.excel_file = None
        for tree in self.tables.values():
            tree.delete(*tree.get_children())
            tree.configure(columns=())
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.summary_var.set("Processing…")
        self.status_var.set("Running QC…")
        self.progress.start(12)
        threading.Thread(target=self._worker, args=(source, level, root, self.multiqc_var.get()), daemon=True).start()

    def _worker(self, source, level, root, html):
        outdir = None
        tail = []
        try:
            root.mkdir(parents=True, exist_ok=True)
            outdir = Path(tempfile.mkdtemp(prefix=datetime.now().strftime("qc_%Y%m%d_%H%M%S_"), dir=root))
            executable = Path(sys.executable)
            if executable.name.lower() == "pythonw.exe":
                executable = executable.with_name("python.exe")
            command = [str(executable), "-u", str(Path(__file__).with_name("msqc2.py")),
                       "--input", str(source), "--output", str(root), "--run-dir", str(outdir), "--level", level]
            if not html:
                command.append("--skip-multiqc")
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, encoding="utf-8", errors="replace",
                                  env={**os.environ, "PYTHONIOENCODING": "utf-8"}, **options) as process:
                for line in process.stdout:
                    self.events.put(("log", line))
                    tail.append(line)
                    if len(tail) > 200:
                        del tail[0]
                code = process.wait()
            if code not in (0, 1) or not (outdir / "QC_summary.xlsx").is_file():
                raise RuntimeError(f"QC failed (exit {code}). See Log or processing.log in the results folder.")
            self.events.put(("done", outdir, level, code == 1))
        except Exception as exc:
            if outdir and not (outdir / "processing.log").is_file():
                try:
                    (outdir / "processing.log").write_text("".join(tail) + "\n" + str(exc), encoding="utf-8")
                except OSError:
                    pass
            self.events.put(("failed", str(exc), outdir))

    def _poll(self):
        try:
            while True:
                kind, *args = self.events.get_nowait()
                if kind == "log":
                    self.log.configure(state="normal")
                    self.log.insert("end", args[0])
                    if int(self.log.index("end-1c").split(".")[0]) > 5000:
                        self.log.delete("1.0", "1001.0")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                else:
                    self._finish()
                    if kind == "done":
                        try:
                            self._show_results(*args)
                        except Exception as exc:
                            self.status_var.set("Results saved, but preview failed: " + str(exc))
                    else:
                        error, outdir = args
                        self.result_dir = outdir
                        self.open_btn.configure(state="normal" if outdir else "disabled")
                        if outdir and (outdir / "QC_summary.xlsx").is_file():
                            self.excel_file = outdir / "QC_summary.xlsx"
                            self.excel_btn.configure(state="normal")
                        self.summary_var.set("QC failed")
                        self.status_var.set(error)
                        messagebox.showerror("QC failed", error)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _finish(self):
        self.busy = False
        self.progress.stop()
        for control in self.controls:
            control.configure(state="normal")
        self.level_box.configure(state="readonly")
        self._level_changed()

    def _show_results(self, outdir, level, partial):
        self.result_dir = outdir
        self.open_btn.configure(state="normal")
        self.excel_file = outdir / "QC_summary.xlsx"
        self.excel_btn.configure(state="normal")
        report = outdir / "multiqc_report.html"
        self.report_file = report if not partial and report.is_file() and report.stat().st_size else None
        self.report_btn.configure(state="normal" if self.report_file else "disabled")
        summary = None
        with pd.ExcelFile(self.excel_file, engine="openpyxl") as workbook:
            for name, tree in self.tables.items():
                if name not in workbook.sheet_names:
                    continue
                df = pd.read_excel(workbook, sheet_name=name, keep_default_na=False, nrows=1000)
                if name == "Summary":
                    summary = df
                columns = [str(i) for i in range(len(df.columns))]
                tree.configure(columns=columns)
                for key, label in zip(columns, df.columns):
                    tree.heading(key, text=label)
                    tree.column(key, width=180, minwidth=100, stretch=False)
                for row in df.itertuples(index=False, name=None):
                    tree.insert("", "end", values=row)
            if level == "PSM" and summary is not None and not summary.empty:
                full_summary = pd.read_excel(workbook, sheet_name="Summary", usecols=["psms"], keep_default_na=False)
                self.summary_var.set(f"Files: {len(full_summary):,}  |  PSM rows: {int(pd.to_numeric(full_summary['psms']).sum()):,}  |  Unique peptide counts are per file; see Summary.")
            elif summary is not None and not summary.empty:
                self.summary_var.set(f"{level} QC complete — {int(summary.iloc[0]['rows']):,} rows")
        note = "Excel complete; PMultiQC failed — see Log and processing.log." if partial else "QC complete."
        self.status_var.set(f"{note} Preview: first 1,000 rows per table. Saved to: {outdir}")

    def open_results(self):
        if self.result_dir:
            os.startfile(str(self.result_dir))

    def open_report(self):
        if self.report_file:
            webbrowser.open(self.report_file.resolve().as_uri())

    def open_excel(self):
        if self.excel_file:
            try:
                os.startfile(str(self.excel_file))
            except OSError as exc:
                messagebox.showerror("Cannot open Excel", f"Open the workbook from the results folder.\n{exc}")

    def _close(self):
        if self.busy:
            messagebox.showinfo("QC running", "Please wait for QC to finish before closing.")
            return
        self.destroy()


if __name__ == "__main__":
    MSQCApp().mainloop()
