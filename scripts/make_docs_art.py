#!/usr/bin/env python3
"""Regenerate the artwork in docs/img/ (logo set, cover, social preview, screenshots).

    pip install playwright && playwright install chromium
    python scripts/make_docs_art.py              # brand images
    python scripts/make_docs_art.py --screenshots  # also dashboard screenshots

Everything is drawn from the SVG mark below and rendered with headless Chromium,
so the images are reproducible. Text uses Inter (falls back to the system sans).
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "docs" / "img"
LOGO = IMG / "logo"
WEB_STATIC = ROOT / "src" / "parcel_tracker" / "web" / "static"

# The project's blue and the palette of its original artwork.
BLUE = "#2447E0"
BLUE_DEEP = "#1A38B8"
BLUE_SOFT = "#4A6BE7"
NAVY = "#1E3A8F"
INK = "#101632"
CREAM = "#F6F1DD"
SKY = "#C6D3FB"
MIST = "#DDE5FD"
RED = "#FF3B2E"
WHITE = "#FFFFFF"

# Face colours of the parcel (top, left, right).
FACES_ON_BLUE = (WHITE, CREAM, SKY)  # light parcel on the blue tile and banners
FACES_ON_LIGHT = (BLUE_SOFT, BLUE, NAVY)  # blue parcel for light backgrounds
FONT = "'Inter', 'Inter Display', system-ui, -apple-system, 'Segoe UI', sans-serif"

# --- the mark ------------------------------------------------------------------
# An isometric parcel (three faces, taped lid) with a location pin badge.
_FACES = (
    "M256 121 L395 190 L256 250 L117 190 Z",
    "M117 218 L238 277 L238 421 L117 362 Z",
    "M274 277 L395 218 L395 362 L274 421 Z",
)
_BOX_TRANSFORM = "translate(-26 18)"
_TAPE = "M186 153 L326 223"
_PIN_RING = (
    "M0 -94 C-54 -94 -90 -55 -90 -6 C-90 46 -31 90 0 123 C31 90 90 46 90 -6 C90 -55 54 -94 0 -94 Z"
)
_PIN = (
    "M0 -74 C-41 -74 -70 -44 -70 -6 C-70 34 -24 71 0 97 C24 71 70 34 70 -6 C70 -44 41 -74 0 -74 Z"
)
_PIN_TRANSFORM = "translate(352 152)"


def mark(
    *,
    faces: tuple[str, str, str] = FACES_ON_BLUE,
    pin: str = RED,
    dot: str = WHITE,
    uid: str = "m",
) -> str:
    """The mark on a transparent background (gaps are real holes, via masks)."""
    face_paths = "".join(
        f'<path d="{d}" fill="{c}" stroke="{c}"/>' for d, c in zip(_FACES, faces, strict=True)
    )
    pin_dot = f'<circle cx="0" cy="-8" r="24" fill="{dot}"/>' if dot != "hole" else ""
    pin_attr = f' mask="url(#{uid}-pin)"' if dot == "hole" else ""
    pin_mask = (
        f'<mask id="{uid}-pin"><rect x="-120" y="-120" width="240" height="260" fill="#fff"/>'
        '<circle cx="0" cy="-8" r="24" fill="#000"/></mask>'
        if dot == "hole"
        else ""
    )
    return (
        f'<defs><mask id="{uid}-box" maskUnits="userSpaceOnUse" x="0" y="0" width="512" height="512">'
        '<rect width="512" height="512" fill="#fff"/>'
        f'<g transform="{_BOX_TRANSFORM}"><path d="{_TAPE}" stroke="#000" stroke-width="24"/></g>'
        f'<g transform="{_PIN_TRANSFORM}"><path d="{_PIN_RING}" fill="#000"/></g>'
        f"</mask>{pin_mask}</defs>"
        f'<g mask="url(#{uid}-box)"><g transform="{_BOX_TRANSFORM}">'
        f'<g stroke-width="18" stroke-linejoin="round">{face_paths}</g>'
        "</g></g>"
        f'<g transform="{_PIN_TRANSFORM}"><path d="{_PIN}" fill="{pin}"{pin_attr}/>{pin_dot}</g>'
    )


def svg(body: str, *, size: int = 512, title: str = "parcel-tracker-bot") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 512 512"><title>{title}</title>{body}</svg>'
    )


def icon_svg(*, radius: int = 112, scale: float = 1.0) -> str:
    """App icon: the light mark on a blue rounded square."""
    inner = mark(uid="i")
    if scale != 1.0:
        offset = 256 * (1 - scale)
        inner = f'<g transform="translate({offset:.1f} {offset:.1f}) scale({scale})">{inner}</g>'
    return svg(f'<rect width="512" height="512" rx="{radius}" fill="{BLUE}"/>{inner}')


# --- page layouts ------------------------------------------------------------------

_BUBBLE = """
<div class="bubble">
  <div class="b-title"><span class="truck">🚚</span> Out for delivery</div>
  <div class="b-name">Ceramic mug · order #1042</div>
  <div class="b-meta">Ada Lovelace — Milano, IT</div>
  <ol class="steps"><li class="on"></li><li class="on"></li><li class="on"></li><li class="on now"></li><li></li></ol>
  <div class="b-row"><span>📍 Bologna hub → Milano</span><span class="time">09:41</span></div>
</div>"""

_CSS = f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: {FONT}; color: {WHITE}; background: {BLUE}; -webkit-font-smoothing: antialiased; }}
.frame {{ position: relative; overflow: hidden; display: flex; align-items: center; }}
.title {{ font-weight: 800; letter-spacing: -0.035em; line-height: 1; }}
.tagline {{ font-weight: 500; letter-spacing: -0.01em; }}
.tagline {{ color: {MIST}; }}
.small {{ font-weight: 500; color: {SKY}; }}
.bubble {{ background: #fff; color: {INK}; border-radius: 28px; border-bottom-left-radius: 8px; box-shadow: 10px 12px 0 {BLUE_DEEP};
  padding: 26px 30px 22px; width: 420px; }}
.b-title {{ font-weight: 700; font-size: 26px; display: flex; align-items: center; gap: 10px; }}
.b-name {{ font-weight: 650; font-size: 22px; margin-top: 16px; }}
.b-meta {{ font-size: 19px; color: #52514e; margin-top: 4px; }}
.steps {{ list-style: none; display: grid; grid-template-columns: repeat(5, 1fr); margin: 22px 4px 18px; position: relative; }}
.steps li {{ position: relative; height: 16px; }}
.steps li::before {{ content: ""; position: absolute; left: 50%; top: 0; width: 16px; height: 16px; margin-left: -8px; border-radius: 50%;
  background: #fff; border: 3px solid #c3c2b7; z-index: 1; }}
.steps li + li::after {{ content: ""; position: absolute; top: 6px; right: 50%; width: 100%; height: 4px; background: #c3c2b7; }}
.steps li.on::before {{ background: {BLUE}; border-color: {BLUE}; }}
.steps li.on::after {{ background: {BLUE}; }}
.steps li.now::before {{ box-shadow: 0 0 0 6px {MIST}; }}
.b-row {{ display: flex; justify-content: space-between; font-size: 18px; color: #52514e; }}
.time {{ color: #898781; }}
"""


def cover_html() -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{_CSS}
.frame {{ width: 1600px; height: 400px; padding: 0 70px; gap: 44px; }}
.logo {{ width: 176px; height: 176px; flex: none; }}
.text {{ flex: 1; min-width: 0; }}
.title {{ font-size: 66px; white-space: nowrap; }}
.tagline {{ font-size: 28px; margin-top: 16px; }}
.small {{ font-size: 19px; margin-top: 18px; }}
.bubble {{ width: 380px; flex: none; padding: 22px 26px 18px; }}
.b-title {{ font-size: 23px; }} .b-name {{ font-size: 20px; margin-top: 12px; }} .b-meta {{ font-size: 17px; }}
.steps {{ margin: 18px 4px 14px; }} .b-row {{ font-size: 16px; }}
</style></head><body><div class="frame">
<svg class="logo" viewBox="0 0 512 512">{mark(uid="c")}</svg>
<div class="text"><div class="title">parcel-tracker-bot</div>
<div class="tagline">Know where every parcel is. Let your customers know too.</div>
<div class="small">Self-hosted Telegram bot + web dashboard · open source (MIT) · one Docker container</div></div>
{_BUBBLE}
</div></body></html>"""


def social_html() -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{_CSS}
.frame {{ width: 1280px; height: 640px; padding: 0 72px; gap: 48px; }}
.left {{ flex: 1; }}
.logo {{ width: 150px; height: 150px; margin-bottom: 26px; }}
.title {{ font-size: 72px; }}
.tagline {{ font-size: 30px; margin-top: 18px; }}
.small {{ font-size: 21px; margin-top: 26px; line-height: 1.45; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 26px; }}
.chips span {{ background: {BLUE_DEEP}; color: #fff; border-radius: 999px; padding: 7px 14px; font-size: 16px; font-weight: 600; white-space: nowrap; }}
.bubble {{ width: 380px; flex: none; }}
</style></head><body><div class="frame">
<div class="left"><svg class="logo" viewBox="0 0 512 512">{mark(uid="s")}</svg>
<div class="title">parcel-tracker-bot</div>
<div class="tagline">Know where every parcel is.<br>Let your customers know too.</div>
<div class="chips"><span>Telegram bot</span><span>Web dashboard</span><span>Tracking pages</span><span>2,000+ carriers via 17track</span></div></div>
{_BUBBLE}
</div></body></html>"""


def telegram_description_html() -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{_CSS}
.frame {{ width: 640px; height: 360px; flex-direction: column; justify-content: center; gap: 0; text-align: center; }}
.logo {{ width: 120px; height: 120px; }}
.title {{ font-size: 40px; margin-top: 12px; }}
.tagline {{ font-size: 21px; margin-top: 10px; }}
.small {{ font-size: 17px; margin-top: 14px; }}
</style></head><body><div class="frame">
<svg class="logo" viewBox="0 0 512 512">{mark(uid="t")}</svg>
<div class="title">Parcel Tracker</div>
<div class="tagline">Send a tracking number. I'll tell you when it moves.</div>
<div class="small">Route maps · delivery alerts · web dashboard for sellers</div>
</div></body></html>"""


# --- rendering ------------------------------------------------------------------------


async def _render_html(page, html: str, path: Path, width: int, height: int, scale: float) -> None:
    await page.set_viewport_size({"width": width, "height": height})
    await page.set_content(html, wait_until="load")
    await page.evaluate("document.fonts.ready")
    await page.screenshot(
        path=str(path),
        clip={"x": 0, "y": 0, "width": width, "height": height},
        omit_background=True,
    )
    print(f"wrote {path.relative_to(ROOT)}")


def _svg_page(svg_text: str, size: int) -> str:
    return (
        "<!doctype html><html><head><style>html,body{margin:0;background:transparent}"
        f"svg{{display:block;width:{size}px;height:{size}px}}</style></head><body>{svg_text}</body></html>"
    )


def write_svgs() -> None:
    LOGO.mkdir(parents=True, exist_ok=True)
    files = {
        LOGO / "icon.svg": icon_svg(),
        LOGO / "mark.svg": svg(mark(faces=FACES_ON_LIGHT, uid="k")),
        LOGO / "mark-light.svg": svg(mark(uid="l")),
        LOGO / "mono-black.svg": svg(mark(faces=("#000",) * 3, pin="#000", dot="hole", uid="b")),
        LOGO / "mono-white.svg": svg(mark(faces=("#fff",) * 3, pin="#fff", dot="hole", uid="w")),
        LOGO / "avatar.svg": icon_svg(radius=0, scale=0.86),
        WEB_STATIC / "logo.svg": icon_svg(),
        WEB_STATIC / "favicon.svg": icon_svg(radius=128),
    }
    for path, text in files.items():
        path.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


async def render_brand() -> None:
    write_svgs()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(device_scale_factor=1)
        for size in (1024, 512):
            await _render_html(
                page, _svg_page(icon_svg(), size), LOGO / f"icon-{size}.png", size, size, 1
            )
        for size in (640, 1280):
            await _render_html(
                page,
                _svg_page(icon_svg(radius=0, scale=0.86), size),
                LOGO / f"avatar-{size}.png",
                size,
                size,
                1,
            )
        for size in (16, 32, 48, 180):
            await _render_html(
                page,
                _svg_page(icon_svg(radius=128 if size < 180 else 0), size),
                LOGO / f"favicon-{size}.png",
                size,
                size,
                1,
            )
        await page.close()
        hi = await browser.new_page(device_scale_factor=2)
        await _render_html(hi, cover_html(), IMG / "cover.png", 1600, 400, 2)
        await hi.close()
        page = await browser.new_page(device_scale_factor=1)
        await _render_html(page, social_html(), IMG / "social-preview.png", 1280, 640, 1)
        await _render_html(
            page, telegram_description_html(), IMG / "telegram-description.png", 640, 360, 1
        )
        await browser.close()


async def render_screenshots() -> None:
    """Dashboard screenshots from the demo data (scripts/demo_web.py)."""
    spec = importlib.util.spec_from_file_location("demo_web", ROOT / "scripts" / "demo_web.py")
    assert spec and spec.loader
    demo = importlib.util.module_from_spec(spec)
    sys.modules["demo_web"] = demo
    spec.loader.exec_module(demo)

    from parcel_tracker.db.migrations import init_schema  # noqa: PLC0415
    from parcel_tracker.web.server import WebServer  # noqa: PLC0415

    port = 8799
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "demo.db")
        await init_schema(db)
        await demo.seed(db)
        bot_data = demo.demo_bot_data(db, port=port, lang="en", maps=False)
        server = WebServer(bot_data, host="127.0.0.1", port=port)
        await server.start()
        try:
            token = await bot_data["web_repo"].create_login_token(demo.OWNER)
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                for scheme in ("light", "dark"):
                    ctx = await browser.new_context(
                        viewport={"width": 1280, "height": 900},
                        device_scale_factor=2,
                        color_scheme=scheme,
                    )
                    page = await ctx.new_page()
                    await page.goto(f"http://127.0.0.1:{port}/login?t={token}")
                    await page.click("button[type=submit]")
                    await page.wait_for_url(f"http://127.0.0.1:{port}/")
                    suffix = "" if scheme == "light" else "-dark"
                    await page.screenshot(path=str(IMG / f"dashboard{suffix}.png"), full_page=False)
                    print(f"wrote docs/img/dashboard{suffix}.png")
                    if scheme == "light":
                        await page.goto(f"http://127.0.0.1:{port}/shipments")
                        await page.screenshot(path=str(IMG / "shipments.png"), full_page=False)
                        await page.goto(f"http://127.0.0.1:{port}/t/demo-share-link")
                        await page.set_viewport_size({"width": 900, "height": 600})
                        await page.screenshot(path=str(IMG / "public-page.png"), full_page=False)
                        print("wrote docs/img/shipments.png, docs/img/public-page.png")
                        token = await bot_data["web_repo"].create_login_token(demo.OWNER)
                    await ctx.close()
                await browser.close()
        finally:
            await server.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--screenshots", action="store_true", help="also capture dashboard screenshots"
    )
    parser.add_argument("--only-screenshots", action="store_true")
    args = parser.parse_args()
    if not args.only_screenshots:
        asyncio.run(render_brand())
    if args.screenshots or args.only_screenshots:
        asyncio.run(render_screenshots())


if __name__ == "__main__":
    main()
