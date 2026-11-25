from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from proteomicsqc.help_docs import find_manual


class HelpDocsTests(unittest.TestCase):
    def test_select_latest_compatible_across_both_layouts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for subdir, version in (("docs", "0.4.0"), ("output/pdf", "0.5.0"), ("docs", "0.6.0")):
                directory = root / subdir
                directory.mkdir(parents=True, exist_ok=True)
                (directory / f"ProteomicsQC_User_Manual_TH_{version}.pdf").write_bytes(b"%PDF-test")
            self.assertEqual(find_manual(root, "0.5.1-dev").parent, root / "output/pdf")
            self.assertIsNone(find_manual(root, "0.3.0"))
            docs_copy = root / "docs/ProteomicsQC_User_Manual_TH_0.5.0.pdf"
            docs_copy.write_bytes(b"%PDF-test")
            self.assertEqual(find_manual(root, "0.5.1-dev"), docs_copy)

    def test_help_button_targets_real_latest_pdf(self):
        from proteomicsqc import __version__
        from proteomicsqc.gui import MSQCApp
        root = Path(__file__).resolve().parents[1]
        expected = find_manual(root, __version__)
        self.assertIsNotNone(expected)
        self.assertEqual(expected.name, "ProteomicsQC_User_Manual_TH_0.5.0.pdf")
        with patch("proteomicsqc.gui.webbrowser.open") as opened:
            MSQCApp.open_manual(object())
            opened.assert_called_once_with(expected.as_uri())


if __name__ == "__main__":
    unittest.main()
