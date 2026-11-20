"""Write the Colab Monitor logo: the dashboard's icons and the README's mark.

    uv run python scripts/make_logo.py

The mark is a radar drawn as a pattern. Dots sit on a polar grid, and the ones the sweep has
just passed are larger, largest at the sweep's head at twelve o'clock and fading over 135
degrees anticlockwise, the way a radar trace fades. The favicon uses a coarser grid with bigger
dots so it still reads at 16 px. The top-right corner stays light: the dashboard draws its
attention dot there on the favicon.

The README shows the mark on its own, black on GitHub's light theme and white on its dark one.

Uses your installed Chrome, or Playwright's Chromium, for the PNG.
"""

import io
import math
import pathlib

from PIL import Image
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "src" / "colab_monitor" / "static"
IMAGES = ROOT / "docs" / "images"
INK = "#ffffff"
GROUND = "#0a0a0a"
CENTRE = 32.0
HEAD = -90.0  # degrees; the sweep points up
TRAIL = 135.0  # degrees the trace fades over, behind the head


def num(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def radar(
    rings: tuple[float, ...],
    spokes: int,
    dim: tuple[float, ...],
    lit: tuple[float, ...],
    centre: float,
    ink: str = INK,
) -> str:
    """Dots on each ring at `spokes` evenly spaced angles, plus one at the centre."""
    dots = [f'<circle cx="{num(CENTRE)}" cy="{num(CENTRE)}" r="{num(centre)}"/>']
    for ring, radius in enumerate(rings):
        for spoke in range(spokes):
            angle = 360 * spoke / spokes - 90
            behind = (HEAD - angle) % 360
            glow = 1 - behind / TRAIL if behind <= TRAIL else 0.0
            r = dim[ring] + (lit[ring] - dim[ring]) * glow
            x = CENTRE + radius * math.cos(math.radians(angle))
            y = CENTRE + radius * math.sin(math.radians(angle))
            dots.append(f'<circle cx="{num(x)}" cy="{num(y)}" r="{num(r)}"/>')
    return f'<g fill="{ink}">{"".join(dots)}</g>'


def tile(mark: str, radius: float, edge: str | None) -> str:
    """The mark on a dark rounded tile; `edge` draws a faint hairline so the tile shows on black."""
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">',
        f'<rect width="64" height="64" rx="{num(radius)}" fill="{GROUND}"/>',
        edge or "",
        mark,
        "</svg>",
    ]
    return "".join(parts)


ICON_GRID = {
    "rings": (9.0, 15.5, 22.0),
    "spokes": 12,
    "dim": (0.75, 0.85, 0.95),
    "lit": (2.4, 2.9, 3.4),
    "centre": 3.2,
}
ICON_MARK = radar(**ICON_GRID)
FAVICON_MARK = radar(rings=(11.0, 21.5), spokes=8, dim=(1.45, 1.6), lit=(4.0, 4.9), centre=4.2)
ICON = tile(
    ICON_MARK,
    15,
    '<rect x="0.5" y="0.5" width="63" height="63" rx="14.5" fill="none" stroke="#fff" stroke-opacity=".16"/>',
)
FAVICON = tile(
    FAVICON_MARK,
    14,
    '<rect x="1" y="1" width="62" height="62" rx="13" fill="none" '
    'stroke="#fff" stroke-opacity=".22" stroke-width="2"/>',
)
# iOS rounds the corners itself, so the home-screen icon is a full square.
TOUCH = tile(ICON_MARK, 0, None)


def bare(ink: str) -> str:
    """The mark alone on a transparent ground, cropped to the dots."""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="6 6 52 52">{radar(**ICON_GRID, ink=ink)}</svg>'


# GitHub's light page is white and its dark page near black; the mark takes the page's text colour.
README_LIGHT = bare("#0a0a0a")
README_DARK = bare("#ffffff")


def png(svg: str, size: int) -> bytes:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome")
        except PlaywrightError:
            browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": size, "height": size})
        sized = svg.replace('viewBox="0 0 64 64"', f'viewBox="0 0 64 64" width="{size}" height="{size}"', 1)
        page.set_content(f'<html><body style="margin:0">{sized}</body></html>')
        shot = page.screenshot(clip={"x": 0, "y": 0, "width": size, "height": size})
        browser.close()
    out = io.BytesIO()
    Image.open(io.BytesIO(shot)).convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


def main() -> None:
    files = {
        STATIC / "icon.svg": ICON,
        STATIC / "favicon.svg": FAVICON,
        IMAGES / "logo-light.svg": README_LIGHT,
        IMAGES / "logo-dark.svg": README_DARK,
    }
    for path, svg in files.items():
        path.write_text(svg + "\n")
        print(f"wrote {path.relative_to(ROOT)}")
    touch = STATIC / "apple-touch-icon.png"
    touch.write_bytes(png(TOUCH, 180))
    print(f"wrote {touch.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
