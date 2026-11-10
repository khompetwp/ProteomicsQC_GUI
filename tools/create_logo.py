"""Reproducible vector-style spectrum/check icon; Pillow is a build dependency only."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def main():
    assets = ROOT / "proteomicsqc" / "assets"
    assets.mkdir(exist_ok=True)
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
<rect x="8" y="8" width="240" height="240" rx="54" fill="#102d46"/>
<path d="M45 176H153M64 176V130M98 176V72M132 176V105" fill="none" stroke="#54d6d0" stroke-width="14" stroke-linecap="round"/>
<circle cx="183" cy="166" r="44" fill="#102d46"/>
<path d="M157 164L176 183L211 144" fill="none" stroke="#a8ea80" stroke-width="15" stroke-linecap="round" stroke-linejoin="round"/>
</svg>'''
    (assets / "logo.svg").write_text(svg, encoding="utf-8")
    scale = 4
    image = Image.new("RGBA", (256 * scale, 256 * scale))
    draw = ImageDraw.Draw(image)
    def box(coords):
        return tuple(value * scale for value in coords)
    draw.rounded_rectangle(box((8, 8, 248, 248)), radius=54 * scale, fill="#102d46")
    def line(points, color, width):
        draw.line([(x * scale, y * scale) for x, y in points], fill=color, width=width * scale, joint="curve")
        radius = width / 2
        for x, y in points:
            draw.ellipse(box((x-radius, y-radius, x+radius, y+radius)), fill=color)
    for points in (((45,176),(153,176)), ((64,176),(64,130)), ((98,176),(98,72)), ((132,176),(132,105))):
        line(points, "#54d6d0", 14)
    draw.ellipse(box((139,122,227,210)), fill="#102d46")
    line(((157,164),(176,183),(211,144)), "#a8ea80", 15)
    image = image.resize((256,256), Image.Resampling.LANCZOS)
    image.save(assets / "logo_256.png")
    image.resize((48,48), Image.Resampling.LANCZOS).save(assets / "logo.png")
    image.save(assets / "logo.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])


if __name__ == "__main__":
    main()
