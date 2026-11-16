# ProteomicsQC 0.5.0 — running from source

Keep msqc_gui.py, msqc2.py, requirements.txt and the entire proteomicsqc folder together.
These application Python files match version 0.5.0.
No input data or previous QC results are replaced.

## Reuse the work computer's PMultiQC environment

Run in PowerShell, replacing the project path with its actual location:

```powershell
cd D:\ProteomicsQC_GUI
& 'C:\ProteomicsQC\.venv313\Scripts\python.exe' -m pip check
& 'C:\ProteomicsQC\.venv313\Scripts\python.exe' msqc_gui.py --self-test
& 'C:\ProteomicsQC\.venv313\Scripts\python.exe' msqc_gui.py
```

The environment path above comes from the earlier screenshot; verify it on that computer.
The self-test prints package versions and confirms that the GUI can be created.
It does not validate reports against real data or enforce the pinned versions.
Do not upgrade an existing shared analysis environment without first checking its versions.
For the exact tested direct dependency versions, use requirements.txt in a new environment.

## New independent environment (Python 3.13 x64 with Tcl/Tk)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe msqc_gui.py --self-test
.\.venv\Scripts\python.exe msqc_gui.py
```

Select the correct Data source: FragPipe, DIA-NN, MaxQuant or Proteome Discoverer.
Proteome Discoverer is available in version 0.5.0: select a
`.mzid` file or folder. HTML requires matching same-folder `.mzML` / `.mgf` files;
uncheck HTML for identification-only Excel. PD abundance Excel is not imported.
See `docs/Proteome_Discoverer.md`.
DIA-NN/MaxQuant reports were tested using synthetic fixtures; confirm compatibility with real exports.
No need to install the upstream search engines when using their existing output files.
