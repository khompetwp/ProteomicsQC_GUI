"""Test actual Inno install/upgrade under a separate test AppId and workspace directory.

The production app's registration/install directory is never targeted.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT.parent / "tmp" / "innosetup" / "compiler" / "ISCC.exe"


def main():
    test = ROOT / "build" / "upgrade_validation" / str(time.time_ns())
    test.mkdir(parents=True)
    target = test / "installed"
    # Deliberately different from the production AppId; constant across the two test versions.
    test_id = "ProteomicsQC.UpgradeVerification." + test.name
    sources = [("0.3.0-preview.3", ROOT / "dist" / "ProteomicsQC_0.3.0-preview.3"),
               ("0.4.0", ROOT / "dist" / "ProteomicsQC_0.4.0")]
    records = []
    sentinel = target / "saved_results" / "keep.txt"
    for index, (version, source) in enumerate(sources):
        script = test / ("install_" + str(index) + ".iss")
        script.write_text(f'''[Setup]
AppId={test_id}
AppName=ProteomicsQC Upgrade Verification
AppVersion={version}
DefaultDirName={target}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={test}
OutputBaseFilename=upgrade_test_{index}
Compression=none
SolidCompression=no
SetupLogging=yes
UninstallDisplayName=ProteomicsQC Upgrade Verification
[Files]
Source: "{source}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs
''', encoding="utf-8-sig")
        subprocess.run([str(COMPILER), "/Qp", str(script)], check=True)
        setup = test / f"upgrade_test_{index}.exe"
        subprocess.run([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CURRENTUSER", f"/DIR={target}", f"/LOG={test / ('install_' + str(index) + '.log')}"], check=True, timeout=180)
        if index == 0:
            sentinel.parent.mkdir()
            sentinel.write_text("preserve existing reports", encoding="utf-8")
        else:
            assert sentinel.read_text(encoding="utf-8") == "preserve existing reports"
        package = target / "_internal" / "app" / "proteomicsqc" / "__init__.py"
        assert f'"{version}"' in package.read_text(encoding="utf-8")
        for relative in ("ProteomicsQC.exe", "_internal/app/proteomicsqc/gui.py", "_internal/app/proteomicsqc/assets/logo.ico"):
            assert hashlib.sha256((source / relative).read_bytes()).digest() == hashlib.sha256((target / relative).read_bytes()).digest()
        check = test / f"self_test_{index}.json"
        subprocess.run([str(target / "ProteomicsQC.exe"), "--self-test", "--output", str(check)], check=True, timeout=90)
        assert json.loads(check.read_text(encoding="utf-8"))["success"]
        records.append({"installed_version": version, "self_test": "passed"})
        # The temporary uncompressed installer is owned by this test; retain the small logs.
        setup.unlink()
    subprocess.run([str(target / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=True, timeout=90)
    assert sentinel.read_text(encoding="utf-8") == "preserve existing reports"
    result = {"versions": records, "report_preserved_after_upgrade_and_uninstall": True,
              "isolated_test_app_id": test_id, "test_directory": str(test),
              "production_app_registration_untouched": True}
    (test / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
