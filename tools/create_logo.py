"""Build application PNG/ICO sizes from the supplied brand logo raster.

The authoritative vector is proteomicsqc/assets/logo.svg. Render that SVG to
logo_512.png with an SVG renderer before running this build-only helper.
"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    assets = ROOT / 'proteomicsqc' / 'assets'
    image = Image.open(assets / 'logo_512.png').convert('RGBA')
    for size, name in ((64, 'logo.png'), (256, 'logo_256.png')):
        image.resize((size, size), Image.Resampling.LANCZOS).save(assets / name)
    image.save(assets / 'logo.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])


if __name__ == '__main__':
    main()
