from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 640, 480

COLORS = {
    "background": "#091119",
    "panel": "#101a22",
    "panel_alt": "#162631",
    "line": "#273944",
    "text": "#e7f0f2",
    "muted": "#8ca3aa",
    "accent": "#1be0a6",
    "accent_dark": "#0d4c42",
    "warning": "#ffb833",
    "danger": "#ff5757",
    "info": "#59adff",
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    windows = Path("C:/Windows/Fonts")
    filename = "seguisb.ttf" if bold else "segoeui.ttf"
    try:
        return ImageFont.truetype(str(windows / filename), size=size)
    except OSError:
        return ImageFont.load_default()


def rounded(draw: ImageDraw.ImageDraw, box, fill, radius=8, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def centered(draw, box, text, text_font, fill):
    left, top, right, bottom = box
    bounds = draw.textbbox((0, 0), text, font=text_font)
    tw = bounds[2] - bounds[0]
    th = bounds[3] - bounds[1]
    draw.text(((left + right - tw) / 2, (top + bottom - th) / 2 - 1), text, font=text_font, fill=fill)


def make_screenshot(path: Path):
    # Release previews are real captures from love.graphics.captureScreenshot.
    # Do not regenerate a mockup that can drift away from the installed UI.
    if not path.is_file():
        raise FileNotFoundError('Capture the current UI on the device before packaging.')
    with Image.open(path) as capture:
        if capture.size != (WIDTH, HEIGHT):
            raise ValueError('The UI capture must be 640x480.')



def make_cover(path: Path):
    source = Image.open(ROOT / "cover-art-r36s-green-led.png").convert("RGB")
    image = ImageOps.fit(source, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
    image.save(path, optimize=True)


make_screenshot(ROOT / "screenshot.png")
make_cover(ROOT / "cover.png")
