"""Start the ProteomicsQC desktop app (or --self-test for portable checks)."""
import sys

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        from proteomicsqc.selftest import main
        sys.exit(main())
    from proteomicsqc.gui import MSQCApp
    MSQCApp().mainloop()
