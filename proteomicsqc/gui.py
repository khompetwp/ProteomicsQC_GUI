"""Tk desktop interface. All analysis runs in a separate process."""
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
import webbrowser

import pandas as pd
from . import __version__
from .adapters import SOURCES, LEVELS as SOURCE_LEVELS
from .outputs import create_run_directory, validate_report_name
from .preferences import load_settings, save_settings
from .preflight import check_input

LEVELS = SOURCE_LEVELS["FragPipe"]

class MSQCApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"ProteomicsQC {__version__}")
        self.geometry("1180x820")
        self.minsize(860, 650)
        import ttkbootstrap as tb
        self.style = tb.Style(theme="bootstrap-light")
        self.style.configure("TFrame", background="#ffffff")
        self.style.configure("TLabel", background="#ffffff", foreground="#203047", font=("Segoe UI", 10))
        self.style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"))
        self.style.configure("Muted.TLabel", foreground="#65758b", font=("Segoe UI", 9))
        self.style.configure("Result.TLabel", font=("Segoe UI", 11, "bold"), foreground="#1763ae")
        self.style.configure("TButton", font=("Segoe UI", 10), padding=(10, 6))
        self.style.configure("primary.TButton", background="#0879d9", bordercolor="#0879d9")
        self.style.configure("Treeview", font=("Segoe UI", 10), rowheight=30)
        self.style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#e8f3fe", foreground="#203047", padding=7)
        self.style.configure("TNotebook.Tab", font=("Segoe UI", 10), padding=(12, 8))
        self.style.map("TNotebook.Tab", foreground=[("selected", "#c6327d")])
        self.configure(background="#ffffff")
        self.preferences = load_settings()
        self.input_var = tk.StringVar()
        self.level_var = tk.StringVar(value="PSM")
        self.source_var = tk.StringVar(value="FragPipe")
        self.output_var = tk.StringVar(value=self.preferences.get("output_folder", ""))
        self.report_name_var = tk.StringVar()
        self.multiqc_var = tk.BooleanVar(value=True)
        self.html_preference = True
        self.status_var = tk.StringVar(value="Ready - select an analysis report to begin.")
        self.summary_var = tk.StringVar(value="Your results will appear here after running QC.")
        self.scope_var = tk.StringVar()
        self.input_hint_var = tk.StringVar()
        self.destination_var = tk.StringVar()
        self.schema_var = tk.StringVar(value="Select an input file or folder.")
        self.job_var = tk.StringVar(value="Ready")
        self.events = queue.Queue()
        self.busy = False
        self.result_dir = self.report_file = self.excel_file = self.active_outdir = None
        self.cancel_requested = threading.Event()
        self.controls = []
        self.validation_id = None
        self.validation_generation = 0
        assets = Path(__file__).with_name("assets")
        self.logo_image = tk.PhotoImage(file=str(assets / "logo.png"))
        self.iconphoto(True, self.logo_image)
        if os.name == "nt":
            self.iconbitmap(str(assets / "logo.ico"))
        main = ttk.Frame(self, padding=(20, 12))
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(6, weight=1)
        heading = ttk.Frame(main, padding=(0, 0, 0, 12))
        heading.grid(row=0, column=0, sticky="ew")
        ttk.Label(heading, image=self.logo_image).pack(side="left", padx=(0, 10))
        ttk.Label(heading, text="ProteomicsQC", style="Title.TLabel").pack(side="left")
        ttk.Button(heading, text="Help / About", command=self.show_help, style="secondary.Outline.TButton").pack(side="right")
        setup = ttk.Frame(main)
        setup.grid(row=1, column=0, sticky="ew")
        for column in (3, 4):
            setup.columnconfigure(column, weight=1)
        ttk.Label(setup, text="Data source").grid(row=0, column=0, sticky="w", pady=5)
        self.source_box = ttk.Combobox(setup, textvariable=self.source_var, values=SOURCES, state="readonly", width=21)
        self.source_box.grid(row=0, column=1, sticky="w", padx=(8, 20))
        ttk.Label(setup, text="Data level").grid(row=0, column=2, sticky="w")
        self.level_box = ttk.Combobox(setup, textvariable=self.level_var, values=LEVELS, state="readonly", width=13)
        self.level_box.grid(row=0, column=3, sticky="w", padx=(8, 12))
        ttk.Label(setup, text="Input file / folder").grid(row=1, column=0, sticky="w", pady=6)
        self.input_entry = ttk.Entry(setup, textvariable=self.input_var)
        self.input_entry.grid(row=1, column=1, columnspan=4, sticky="ew", padx=(8, 10))
        self.controls.append(self.input_entry)
        self._button(setup, "File…", self.browse_input, 1, 5)
        self._button(setup, "Folder…", self.browse_folder, 1, 6)
        ttk.Label(setup, textvariable=self.input_hint_var, style="Muted.TLabel", wraplength=940).grid(row=2, column=1, columnspan=6, sticky="w", padx=8)
        ttk.Label(setup, text="Output folder").grid(row=3, column=0, sticky="w", pady=6)
        entry = ttk.Entry(setup, textvariable=self.output_var)
        entry.grid(row=3, column=1, columnspan=5, sticky="ew", padx=(8, 10))
        self.controls.append(entry)
        self._button(setup, "Browse…", self.browse_output, 3, 6)
        ttk.Label(setup, text="Report folder name").grid(row=4, column=0, sticky="w", pady=6)
        entry = ttk.Entry(setup, textvariable=self.report_name_var)
        entry.grid(row=4, column=1, columnspan=3, sticky="ew", padx=(8, 10))
        self.controls.append(entry)
        ttk.Label(setup, text="Optional; blank = automatic name", style="Muted.TLabel").grid(row=4, column=4, columnspan=3, sticky="w")
        options = ttk.Frame(main, padding=(0, 8, 0, 8))
        options.grid(row=2, column=0, sticky="ew")
        options.columnconfigure(0, weight=1)
        self.multiqc_check = ttk.Checkbutton(options, text="Create PMultiQC HTML report", variable=self.multiqc_var, command=self._html_changed)
        self.multiqc_check.grid(row=0, column=0, sticky="w")
        self.run_btn = ttk.Button(options, text="Run QC", command=self.run_qc, style="primary.TButton", width=15)
        self.run_btn.grid(row=0, column=1, padx=(10, 8))
        self.controls.append(self.run_btn)
        self.cancel_btn = ttk.Button(options, text="Cancel", command=self.cancel_qc, state="disabled", style="secondary.Outline.TButton")
        self.cancel_btn.grid(row=0, column=2)
        ttk.Label(options, textvariable=self.destination_var, style="Muted.TLabel", wraplength=980).grid(row=1, column=0, columnspan=3, sticky="w", pady=(7, 0))
        ttk.Label(options, textvariable=self.schema_var, style="Muted.TLabel", wraplength=980).grid(row=2, column=0, columnspan=3, sticky="w", pady=(3, 0))
        ttk.Separator(main).grid(row=3, column=0, sticky="ew", pady=(0, 10))
        results = ttk.Frame(main)
        results.grid(row=4, column=0, sticky="ew", pady=(0, 5))
        results.columnconfigure(1, weight=1)
        self.job_label = ttk.Label(results, textvariable=self.job_var, style="Result.TLabel")
        self.job_label.grid(row=0, column=0, sticky="w", padx=(0, 15))
        ttk.Label(results, textvariable=self.summary_var, wraplength=750).grid(row=0, column=1, sticky="w")
        tools = ttk.Frame(main)
        tools.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        self.excel_btn = ttk.Button(tools, text="Open Excel", command=self.open_excel, state="disabled", style="secondary.Outline.TButton")
        self.report_btn = ttk.Button(tools, text="Open HTML", command=self.open_report, state="disabled", style="secondary.Outline.TButton")
        self.open_btn = ttk.Button(tools, text="Open folder", command=self.open_results, state="disabled", style="secondary.Outline.TButton")
        for button in (self.excel_btn, self.report_btn, self.open_btn):
            button.pack(side="left", padx=(0, 8))
        self.progress = ttk.Progressbar(tools, mode="indeterminate", length=160)
        self.progress.pack(side="right", padx=(10, 0))
        self.tabs = ttk.Notebook(main)
        self.tabs.grid(row=6, column=0, sticky="nsew")
        self.tables = {}
        for name in ("Summary", "By run", "Numeric audit", "Missing values", "Input files", "Run info"):
            frame = ttk.Frame(self.tabs)
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            tree = ttk.Treeview(frame, show="headings")
            tree.grid(row=0, column=0, sticky="nsew")
            ys = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            xs = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
            ys.grid(row=0, column=1, sticky="ns")
            xs.grid(row=1, column=0, sticky="ew")
            tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
            self.tabs.add(frame, text=name)
            self.tables[name] = tree
            if name == "Summary":
                self.run_preview_frame = ttk.Labelframe(frame, text="By run preview (first 6 runs)", padding=8)
                self.run_preview_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
                self.run_preview = ttk.Treeview(self.run_preview_frame, show="headings", height=4)
                self.run_preview.pack(fill="x", expand=True)
                self.run_preview_frame.grid_remove()
        log_frame = ttk.Frame(self.tabs)
        ttk.Button(log_frame, text="Copy log / error", command=self.copy_log, style="secondary.Outline.TButton").pack(anchor="e", pady=5)
        self.log = tk.Text(log_frame, height=10, wrap="word", state="disabled", font=("Consolas", 10), background="#f7f9fc", foreground="#24364b", relief="flat")
        self.log.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scroll.set)
        self.tabs.add(log_frame, text="Log")
        ttk.Label(main, textvariable=self.status_var, style="Muted.TLabel", wraplength=1000).grid(row=7, column=0, sticky="w", pady=(8, 0))
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.source_var.trace_add("write", self._source_changed)
        self.level_var.trace_add("write", self._level_changed)
        for variable in (self.input_var, self.output_var, self.report_name_var):
            variable.trace_add("write", self._scope_changed)
        self._scope_changed()
        self.poll_id = self.after(100, self._poll)

    def _scope_changed(self, *args):
        selected = self.input_var.get().strip().strip('"')
        hints = {"FragPipe": "PSM: select any TSV filename, or a folder containing psm*.tsv. Peptide/Protein: select one TSV file.",
                 "DIA-NN": "Select a main .parquet / .tsv report, not a matrix or spectral library. Target schema: DIA-NN 2.2.0.",
                 "MaxQuant": "Select the txt folder containing evidence.txt, msms.txt and proteinGroups.txt (standard filenames).",
                 "Proteome Discoverer": "Select a .mzid or a folder of .mzid files. HTML: same-folder, same-name .mzML/.mgf pairs. Excel: identification only; PD abundance Excel is not imported."}
        self.input_hint_var.set(hints[self.source_var.get()])
        try:
            source = Path(selected).expanduser() if selected else None
            output = self.output_var.get().strip().strip('"')
            root = Path(output).expanduser() if output else ((source if source.is_dir() else source.parent) / "ResultQC" if source else None)
            name = validate_report_name(self.report_name_var.get())
            target = str(root / name) if root and name else (str(root) + " / [automatic run folder]" if root else "Select input or choose Output folder")
            self.destination_var.set("Output: " + target)
        except (OSError, ValueError) as exc:
            self.destination_var.set("Output: " + str(exc))
        self.scope_var.set("Excel retains all input rows. PMultiQC uses its own metric rules. Optional supporting files are scanned from the input folder.")
        if self.validation_id:
            self.after_cancel(self.validation_id)
        self.validation_generation += 1
        if selected and not self.busy:
            self.schema_var.set("Checking input structure and file pairs…")
            self.validation_id = self.after(450, self._validate_async)
        elif not selected:
            self.schema_var.set("Select an input file or folder.")

    def _validate_async(self):
        self.validation_id = None
        generation = self.validation_generation
        source = Path(self.input_var.get().strip().strip('"')).expanduser()
        data_source, level, html = self.source_var.get(), self.level_var.get(), self.multiqc_var.get()
        def work():
            try:
                files, warnings = check_input(source, data_source, level, html=html)
                text = "Input checked: " + str(len(files)) + " file(s). " + (" ".join(warnings) if warnings else "Required columns found; no quality PASS/FAIL decision is made.")
            except Exception as exc:
                text = "Check input: " + str(exc)
            self.events.put(("validation", generation, text))
        threading.Thread(target=work, daemon=True).start()

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

    def _level_changed(self, *args):
        psm = self.source_var.get() != "FragPipe" or self.level_var.get() == "PSM"
        if not psm:
            self.multiqc_var.set(False)
        elif not getattr(self, "_html_available", True):
            self.multiqc_var.set(self.html_preference)
        self._html_available = psm
        self.multiqc_check.configure(state="normal" if psm and not self.busy else "disabled")
        self._scope_changed()

    def _html_changed(self):
        self.html_preference = self.multiqc_var.get()
        self._scope_changed()

    def _remember(self, source=None):
        if source:
            self.preferences["input_folder"] = str(source if source.is_dir() else source.parent)
        self.preferences["output_folder"] = self.output_var.get().strip().strip('"')
        try:
            save_settings(self.preferences)
        except OSError as exc:
            self.status_var.set("Settings could not be saved: " + str(exc))

    def browse_input(self):
        types = {"FragPipe": "*.tsv", "DIA-NN": "*.parquet *.tsv", "MaxQuant": "*.txt", "Proteome Discoverer": "*.mzid"}
        selected = filedialog.askopenfilename(title="Select " + self.source_var.get() + " report", initialdir=self.preferences.get("input_folder", ""), filetypes=[("Proteomics reports", types[self.source_var.get()]), ("All files", "*.*")])
        if selected:
            self.input_var.set(selected)
            self._remember(Path(selected))

    def browse_folder(self):
        selected = filedialog.askdirectory(title="Select analysis output folder", initialdir=self.preferences.get("input_folder", ""))
        if selected:
            self.input_var.set(selected)
            self.level_var.set(SOURCE_LEVELS[self.source_var.get()][0])
            self._level_changed()
            self._remember(Path(selected))

    def browse_output(self):
        selected = filedialog.askdirectory(title="Select output folder", initialdir=self.preferences.get("output_folder", ""))
        if selected:
            self.output_var.set(selected)
            self._remember()

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
        self._remember(source)
        self.job_var.set("Checking input")
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
        self.run_preview_frame.grid_remove()
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
            self.events.put(("stage", "Checking input columns"))
            folder = source if source.is_dir() else source.parent
            excluded = (root,) if root != folder and folder in root.parents else ()
            files, warnings = check_input(source, data_source, level, excluded=excluded, html=html)
            self.events.put(("log", f"Input headers checked: {len(files)} file(s).\n"))
            for warning in warnings:
                self.events.put(("log", "WARNING: " + warning + "\n"))
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
                    if line.startswith("Reading"):
                        self.events.put(("stage", "Reading input data"))
                    elif "PMultiQC scan folder:" in line:
                        self.events.put(("stage", "Creating PMultiQC HTML"))
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
                if kind == "validation":
                    if args[0] == self.validation_generation and not self.busy:
                        self.schema_var.set(args[1])
                    continue
                elif kind == "stage":
                    self.job_var.set(args[0])
                    continue
                elif kind == "log":
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
                        self.job_var.set("Cancelled")
                        self.result_dir = args[0]
                        self.open_btn.configure(state="normal")
                        self.summary_var.set("Analysis cancelled")
                        self.status_var.set(f"Cancelled. Run history saved to: {self.result_dir}")
                    else:
                        error, outdir = args
                        self.job_var.set("Failed")
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
        if getattr(self, "validation_id", None):
            self.after_cancel(self.validation_id)
            self.validation_id = None
        if getattr(self, "poll_id", None):
            self.after_cancel(self.poll_id)
            self.poll_id = None
        self.update_idletasks()
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
        self.job_var.set("Excel complete; HTML incomplete" if partial else "Processing complete")
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
                    wanted = {"FragPipe": ("source_file", "psms", "unique_peptide_sequences", "median_charge", "rows", "unique_peptides", "unique_protein_identifiers"),
                              "DIA-NN": ("source_file", "input_rows", "unique_precursors", "unique_peptide_sequences", "protein_group_strings"),
                              "MaxQuant": ("selected_level", "rows", "psm_rows", "protein_group_rows"),
                              "Proteome Discoverer": ("source_file", "psm_items", "rank1_passing_items", "unique_peptide_sequences", "referenced_protein_accessions", "paired_spectrum_file")}[data_source]
                    df = df[[column for column in wanted if column in df]].copy()
                    if "source_file" in df:
                        df["source_file"] = df.source_file.map(lambda value: Path(str(value)).name)
                columns = [str(i) for i in range(len(df.columns))]
                tree.configure(columns=columns)
                for key, label in zip(columns, df.columns):
                    display = {"source_file": "Input file", "psms": "PSM rows", "unique_peptide_sequences": "Unique peptides per file" if name == "Summary" else "Unique peptides per run", "input_rows": "Precursor observations", "rows": "Rows"}.get(label, label.replace("_", " ").capitalize())
                    tree.heading(key, text=display)
                    tree.column(key, width=220 if label == "source_file" else 190, minwidth=110, stretch=True)
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
            elif data_source == "Proteome Discoverer" and summary is not None and not summary.empty:
                all_counts = pd.read_excel(workbook, sheet_name="Summary", usecols=["psm_items"])
                self.summary_var.set(f"PD identification QC | Items retained: {int(all_counts.psm_items.sum()):,} | Includes all ranks and threshold flags; no abundance import")
            elif summary is not None and not summary.empty:
                self.summary_var.set(f"{level} QC complete — {int(summary.iloc[0]['rows']):,} rows")
            if "By run" in workbook.sheet_names:
                runs = pd.read_excel(workbook, sheet_name="By run", keep_default_na=False, nrows=6)
                wanted = ("run", "psms", "unique_peptide_sequences", "median_charge") if data_source == "FragPipe" else (("run", "input_rows", "unique_precursors", "unique_peptide_sequences") if data_source == "DIA-NN" else ("run", "evidence_rows", "psm_rows", "mbr_evidence_rows"))
                if data_source == "Proteome Discoverer":
                    wanted = ("run", "psm_items", "rank1_passing_items", "unique_peptide_sequences")
                runs = runs[[column for column in wanted if column in runs]]
                if not runs.empty:
                    self.run_preview.configure(columns=list(runs.columns))
                    self.run_preview.delete(*self.run_preview.get_children())
                    for column in runs:
                        label = {"psms": "PSM rows", "input_rows": "Precursor observations", "unique_peptide_sequences": "Unique peptides per run"}.get(column, column.replace("_", " ").capitalize())
                        self.run_preview.heading(column, text=label)
                        self.run_preview.column(column, width=190, minwidth=100, stretch=True)
                    for row in runs.itertuples(index=False, name=None):
                        self.run_preview.insert("", "end", values=row)
                    self.run_preview_frame.grid()
        note = "Excel complete; PMultiQC failed or incomplete - see Log and processing.log." if partial else "QC complete."
        self.status_var.set(f"{note} Preview: first 1,000 rows per table. Saved to: {outdir}")

    def copy_log(self):
        text = self.log.get("1.0", "end").strip() or self.status_var.get()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Log copied. Review paths and identifiers before sharing.")

    def show_help(self):
        window = tk.Toplevel(self)
        window.title("Help / About - ProteomicsQC")
        window.geometry("650x430")
        window.transient(self)
        frame = ttk.Frame(window, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"ProteomicsQC {__version__}", style="Result.TLabel").pack(anchor="w", pady=(0, 14))
        text = "1. Select Data source, input file/folder and Data level.\n2. Choose Output folder and a new Report folder name.\n3. HTML is enabled by default; uncheck for Excel only.\n4. Run QC, then open Excel, HTML or the results folder.\n\nExcel retains all input rows; PMultiQC has its own metric rules.\nProcessing complete does not mean scientific PASS/FAIL.\n\nSettings: " + str(__import__('proteomicsqc.preferences', fromlist=['settings_file']).settings_file())
        ttk.Label(frame, text=text, wraplength=590, justify="left").pack(anchor="w", fill="x")
        ttk.Button(frame, text="Open PDF manual", command=self.open_manual).pack(anchor="w", pady=15)
        ttk.Button(frame, text="Close", command=window.destroy).pack(anchor="e")

    def open_manual(self):
        root = Path(__file__).resolve().parents[1]
        candidates = (root / "docs" / "ProteomicsQC_User_Manual_TH_0.4.0.pdf", root / "output" / "pdf" / "ProteomicsQC_User_Manual_TH_0.4.0.pdf")
        for path in candidates:
            if path.is_file():
                webbrowser.open(path.as_uri())
                return
        messagebox.showinfo("PDF manual", "The PDF manual is not present in this source copy. Download it from the GitHub release.")

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

