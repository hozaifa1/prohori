"""Shared palette + font helpers for the demo-video assets (matches service/static/style.css, dark theme)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "video" / "assets"
FONT_SRC = ROOT / "service" / "static" / "fonts"
FONT_OUT = ASSETS / "tmp" / "fonts"

# dark theme tokens from service/static/style.css
BG = "#0a121a"
SURFACE = "#111c27"
SURFACE2 = "#1a2838"
LINE = "#263648"
TEXT = "#e8eef4"
MUTED = "#9db0c1"
AMBER = "#ffbf3c"
OK = "#46d27a"
BAD = "#ff7a6e"
OK_BG = "#10281b"
WARN_BG = "#2d2310"
BAD_BG = "#331816"
BLUE = "#6fb2ff"  # neutral comparison colour (not in the app palette; used for baselines)

W, H = 1920, 1080


def make_ttf() -> dict[str, Path]:
    """Instantiate static TTFs (regular 400, semibold 600, bold 750, mono 500) from the variable woff2 fonts."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    FONT_OUT.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    specs = {
        "Geist-Regular": ("geist-latin-wght-normal.woff2", 400),
        "Geist-SemiBold": ("geist-latin-wght-normal.woff2", 600),
        "Geist-Bold": ("geist-latin-wght-normal.woff2", 750),
        "GeistMono-Medium": ("geist-mono-latin-wght-normal.woff2", 500),
    }
    for name, (src, wght) in specs.items():
        dst = FONT_OUT / f"{name}.ttf"
        if not dst.exists():
            f = TTFont(FONT_SRC / src)
            f = instancer.instantiateVariableFont(f, {"wght": wght})
            f.flavor = None
            f.save(dst)
        out[name] = dst
    return out


def setup_matplotlib():
    import matplotlib
    from matplotlib import font_manager as fm

    matplotlib.use("Agg")
    fonts = make_ttf()
    for p in fonts.values():
        fm.fontManager.addfont(str(p))
    # family names as stored in the font files
    reg = fm.FontProperties(fname=str(fonts["Geist-Regular"])).get_name()
    matplotlib.rcParams.update({
        "font.family": reg,
        "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
        "text.color": TEXT, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.edgecolor": LINE, "grid.color": LINE, "axes.spines.top": False, "axes.spines.right": False,
        "figure.figsize": (19.2, 10.8), "figure.dpi": 100,
    })
    return fonts
