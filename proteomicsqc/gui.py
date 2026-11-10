"""Tk desktop interface. All analysis runs in a separate process."""
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

import pandas as pd
from . import __version__
from .adapters import SOURCES, LEVELS as SOURCE_LEVELS
from .outputs import create_run_directory, validate_report_name

LEVELS = SOURCE_LEVELS["FragPipe"]

class MSQCApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"ProteomicsQC {__version__}")
        self.geometry("1160x810")
        self.minsize(820, 580)
        self.input_var = tk.StringVar()
        self.level_var = tk.StringVar(value="PSM")
        self.source_var = tk.StringVar(value="FragPipe")
        self.source_var.trace_add("write", self._source_changed)
        self.output_var = tk.StringVar()
        self.report_name_var = tk.StringVar()
        assets = Path(__file__).with_name("assets")
        self.logo_image = tk.PhotoImage(file=str(assets / "logo.png"))
        self.iconphoto(True, self.logo_image)
        if os.name == "nt":
            self.iconbitmap(str(assets / "logo.ico"))
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
        self.active_outdir = None
        self.cancel_requested = threading.Event()
        self.controls = []
        main = ttk.Frame(self, padding=18)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(8, weight=1)
        heading = ttk.Frame(main)
        heading.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 14))
        ttk.Label(heading, image=self.logo_image).pack(side="left", padx=(0, 10))
        ttk.Label(heading, text="ProteomicsQC", font=("Segoe UI", 19, "bold")).pack(side="left", padx=(0, 24))
        ttk.Label(heading, text="Data source").pack(side="left", padx=(0, 8))
        self.source_box = ttk.Combobox(heading, textvariable=self.source_var, values=SOURCES, state="readonly", width=15)
        self.source_box.pack(side="left")
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
        ttk.Label(main, text="Output parent folder").grid(row=3, column=0, sticky="w")
        entry = ttk.Entry(main, textvariable=self.output_var)
        entry.grid(row=3, column=1, sticky="ew", padx=10, pady=5)
        self.controls.append(entry)
        self._button(main, "Browse…", self.browse_output, 3, 2)
        self.multiqc_check = ttk.Checkbutton(main, text="Create PMultiQC HTML report (uses PMultiQC's own metric rules)", variable=self.multiqc_var)
        naming = ttk.Frame(main)
        naming.grid(row=4, column=0, columnspan=4, sticky="ew", pady=5)
        ttk.Label(naming, text="Report folder name").pack(side="left")
        name_entry = ttk.Entry(naming, textvariable=self.report_name_var, width=38)
        name_entry.pack(side="left", padx=10)
        self.controls.append(name_entry)
        ttk.Label(naming, text="Optional; blank = automatic name").pack(side="left")
        self.multiqc_check.grid(row=5, column=1, columnspan=3, sticky="w", padx=10, pady=5)
        ttk.Label(main, textvariable=self.scope_var, wraplength=1000, foreground="#555555").grid(row=6, column=0, columnspan=4, sticky="w", pady=5)
        actions = ttk.Frame(main)
        actions.grid(row=7, column=0, columnspan=4, sticky="ew", pady=10)
        self.run_btn = ttk.Button(actions, text="Run QC", command=self.run_qc)
        self.run_btn.pack(side="left")
        self.controls.append(self.run_btn)
        self.cancel_btn = ttk.Button(actions, text="Cancel", command=self.cancel_qc, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))
        self.open_btn = ttk.Button(actions, text="Open results folder", command=self.open_results, state="disabled")
        self.open_btn.pack(side="left", padx=8)
        self.excel_btn = ttk.Button(actions, text="Open Excel summary", command=self.open_excel, state="disabled")
        self.excel_btn.pack(side="left", padx=(0, 8))
        self.report_btn = ttk.Button(actions, text="Open HTML report", command=self.open_report, state="disabled")
        self.report_btn.pack(side="left")
        self.progress = ttk.Progressbar(actions, mode="indeterminate")
        self.progress.pack(side="right", fill="x", expand=True, padx=(20, 0))
        ttk.Label(main, textvariable=self.summary_var, wraplength=1000, font=("Segoe UI", 10, "bold")).grid(row=8, column=0, columnspan=4, sticky="w", pady=(0, 10))
        tabs = ttk.Notebook(main)
        main.rowconfigure(8, weight=0)
        main.rowconfigure(9, weight=1)
        tabs.grid(row=9, column=0, columnspan=4, sticky="nsew")
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
        ttk.Label(main, textvariable=self.status_var, wraplength=1000).grid(row=10, column=0, columnspan=4, sticky="w", pady=(10, 0))
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._scope_changed()
        self.poll_id = self.after(100, self._poll)

    def _scope_changed(self, *args):
        selected = self.input_var.get().strip().strip('"')
        note = "Output: QC_summary.xlsx; HTML optional; report support files stay in _support/."
        if self.multiqc_var.get():
            if selected:
                path = Path(selected).expanduser()
                scan = path.parent if path.is_file() else path
                note += f"\n{self.source_var.get()}: PMultiQC scans supporting files in the input folder; PSM/main reports use the selected input. Input: {scan}"
            else:
                note += "\nPMultiQC scans the whole selected folder (or the selected file's parent)."
        else:
            note += "\nNo HTML requested. Input files are preserved; no QC filtering is applied."
        self.scope_var.set(note)

    def _source_changed(self, *args):
        source = self.source_var.get()
        if not hasattr(self, "level_box"):
            return
        levels = SOURCE_LEVELS[source]
        self.level_box.configure(values=levels)
        self.level_var.set(levels[0])
        self._level_changed()
        self._scope_changed()

    def _button(self, parent, text, command, row, column):
        button = ttk.Button(parent, text=text, command=command)
        button.grid(row=row, column=column, padx=4)
        self.controls.append(button)

    def _level_changed(self, event=None):
        psm = self.source_var.get() != "FragPipe" or self.level_var.get() == "PSM"
        if not psm:
            self.multiqc_var.set(False)
        self.multiqc_check.configure(state="normal" if psm and not self.busy else "disabled")

    def browse_input(self):
        selected = filedialog.askopenfilename(title="Select report file", filetypes=[("Proteomics reports", "*.tsv *.parquet *.txt"), ("All files", "*.*")])
        if selected:
            self.input_var.set(selected)

    def browse_folder(self):
        selected = filedialog.askdirectory(title="Select analysis output folder")
        if selected:
            self.input_var.set(selected)
            self.level_var.set(SOURCE_LEVELS[self.source_var.get()][0])
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
            data_source = self.source_var.get()
            if data_source == "FragPipe" and level != "PSM" and (not source.is_file() or source.suffix.lower() != ".tsv"):
                raise ValueError("Peptide and Protein modes require a single TSV file.")
            if data_source == "FragPipe" and level == "PSM" and source.is_file() and source.suffix.lower() != ".tsv":
                raise ValueError("PSM mode requires a FragPipe TSV file (any filename).")
            if not Path(__file__).resolve().parents[1].joinpath("msqc2.py").is_file():
                raise ValueError("Place msqc2.py in the same folder as this GUI.")
            try:
                import openpyxl
            except ImportError:
                raise ValueError("Excel output requires openpyxl. Install requirements.txt in this Python environment.")
            output = self.output_var.get().strip().strip('"')
            root = Path(output).expanduser().resolve() if output else (source if source.is_dir() else source.parent) / "ResultQC"
            report_name = validate_report_name(self.report_name_var.get())
            if report_name and (root / report_name).exists():
                raise ValueError("Report folder already exists. Choose a new name; previous results are preserved.")
        except (OSError, ValueError) as exc:
            messagebox.showwarning("Check input", str(exc))
            return
        self.busy = True
        self.cancel_requested.clear()
        self.active_outdir = None
        self.cancel_btn.configure(state="normal")
        for control in self.controls:
            control.configure(state="disabled")
        self.level_box.configure(state="disabled")
        self.source_box.configure(state="disabled")
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
        threading.Thread(target=self._worker, args=(source, level, root, self.multiqc_var.get(), data_source, report_name), daemon=True).start()

    def _worker(self, source, level, root, html, data_source="FragPipe", report_name=""):
        outdir = None
        tail = []
        try:
            outdir = create_run_directory(root, report_name)
            self.active_outdir = outdir
            if self.cancel_requested.is_set():
                (outdir / ".cancel_requested").touch()
            executable = Path(sys.executable)
            if executable.name.lower() == "pythonw.exe":
                executable = executable.with_name("python.exe")
            command = [str(executable), "-E", "-s", "-u", str(Path(__file__).resolve().parents[1] / "msqc2.py"),
                       "--input", str(source), "--output", str(root), "--run-dir", str(outdir), "--level", level, "--source", data_source]
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
            if code == 130:
                self.events.put(("cancelled", outdir))
                return
            if code not in (0, 1) or not (outdir / "QC_summary.xlsx").is_file():
                raise RuntimeError(f"QC failed (exit {code}). See Log or processing.log in the results folder.")
            self.events.put(("done", outdir, level, code == 1, data_source))
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
                    elif kind == "cancelled":
                        self.result_dir = args[0]
                        self.open_btn.configure(state="normal")
                        self.summary_var.set("Analysis cancelled")
                        self.status_var.set(f"Cancelled. Run history saved to: {self.result_dir}")
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
        self.poll_id = self.after(100, self._poll)

    def destroy(self):
        if getattr(self, "poll_id", None):
            self.after_cancel(self.poll_id)
            self.poll_id = None
        super().destroy()

    def _finish(self):
        self.busy = False
        self.progress.stop()
        self.cancel_btn.configure(state="disabled")
        self.active_outdir = None
        for control in self.controls:
            control.configure(state="normal")
        self.level_box.configure(state="readonly")
        self.source_box.configure(state="readonly")
        self._level_changed()

    def _show_results(self, outdir, level, partial, data_source="FragPipe"):
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
            if data_source == "FragPipe" and level == "PSM" and summary is not None and not summary.empty:
                full_summary = pd.read_excel(workbook, sheet_name="Summary", usecols=["psms"], keep_default_na=False)
                self.summary_var.set(f"Files: {len(full_summary):,}  |  PSM rows: {int(pd.to_numeric(full_summary['psms']).sum()):,}  |  Unique peptide counts are per file; see Summary.")
            elif data_source == "DIA-NN" and summary is not None and not summary.empty:
                self.summary_var.set(f"DIA-NN QC complete | Precursor observations: {int(summary.iloc[0]['input_rows']):,} | All input rows retained")
            elif data_source == "MaxQuant" and summary is not None and not summary.empty:
                counts = pd.read_excel(workbook, sheet_name="By run", usecols=["evidence_rows", "psm_rows"])
                self.summary_var.set(f"MaxQuant QC complete | Evidence rows: {int(counts.evidence_rows.sum()):,} | MS/MS PSM rows: {int(counts.psm_rows.sum()):,}")
            elif summary is not None and not summary.empty:
                self.summary_var.set(f"{level} QC complete — {int(summary.iloc[0]['rows']):,} rows")
        note = "Excel complete; PMultiQC failed or incomplete - see Log and processing.log." if partial else "QC complete."
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

    def cancel_qc(self):
        if self.busy:
            self.cancel_requested.set()
            if self.active_outdir:
                try:
                    (self.active_outdir / ".cancel_requested").touch()
                except OSError as exc:
                    messagebox.showerror("Cancellation failed", str(exc))
                    return
            self.cancel_btn.configure(state="disabled")
            self.status_var.set("Cancelling... waiting for the current table read to finish.")

    def _close(self):
        if self.busy:
            messagebox.showinfo("QC running", "Please wait for QC to finish before closing.")
            return
        self.destroy()

