"""Generate 32-bit account icons without palette quantization."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
TRAY = ROOT / "tray"


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (Path(r"C:\Windows\Fonts\segoeuib.ttf"), Path(r"C:\Windows\Fonts\arialbd.ttf")):
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _write(name: str, rgb: tuple[int, int, int], letter: str) -> None:
    canvas = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((4, 4, 124, 124), fill=rgb + (255,))
    # The shell commonly renders this 32px icon at 16px.  A larger source
    # glyph keeps the account letter legible in Explorer and the tray.
    font = _font(96)
    box = draw.textbbox((0, 0), letter, font=font)
    draw.text(((128 - (box[2] - box[0])) / 2, (128 - (box[3] - box[1])) / 2 - box[1] - 4), letter, font=font, fill=(255, 255, 255, 255))
    canvas.save(TRAY / name, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)])


def main() -> int:
    _write("BigQMT_Simulation_90000001.ico", (50, 169, 232), "S")
    _write("BigQMT_Production_ReadOnly_90000002.ico", (20, 58, 122), "P")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
