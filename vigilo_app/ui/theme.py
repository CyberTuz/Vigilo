"""
Colours, icons (Windows Segoe icon font) and image helpers of the user interface.
"""

import os

import cv2
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import customtkinter as ctk

from ..common import APP_ICO


# ----------------------------------------------------------------------------- theme
BG = "#0e1014"
PANEL = "#161920"
CARD = "#1d2129"
CARD_HOVER = "#272c37"
CARD_SEL = "#22304a"
INPUT = "#12151b"
BORDER = "#2a303c"
TXT = "#e8eaf0"
MUTED = "#8b93a5"
ACCENT = "#3b82f6"
ACCENT_H = "#2563eb"
GREEN = "#22c55e"
RED = "#ef4444"
RED_D = "#dc2626"
RED_DH = "#b91c1c"
ORANGE = "#f59e0b"
TILE_BG = "#07080b"

ICON_CHARS = {
    "add": "\uE710", "search": "\uE721", "record": "\uE7C8", "stop": "\uE71A",
    "folder": "\uE838", "settings": "\uE713", "camera": "\uE722", "edit": "\uE70F",
    "delete": "\uE74D", "full": "\uE740", "back": "\uE73F", "grid": "\uE8A9",
    "webcam": "\uE8B8", "more": "\uE712", "check": "\uE73E", "warning": "\uE7BA",
    "disk": "\uEDA2", "network": "\uE968", "eye": "\uE7B3", "plug": "\uE703",
    "refresh": "\uE72C", "info": "\uE946", "window": "\uE737", "video": "\uE714",
    "play": "\uE768", "pause": "\uE769", "prev": "\uE892", "next": "\uE893",
    "history": "\uE81C", "calendar": "\uE787", "export": "\uEDE1",
    "up": "\uE70E", "down": "\uE70D", "left": "\uE76B", "right": "\uE76C",
    "clock": "\uE823", "motion": "\uE805", "pin": "\uE718",
}
ICON_CHARS.update({"volume": chr(0xE767), "mute": chr(0xE74F), "globe": chr(0xE774)})


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _find_icon_font():
    fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for f in ("SegoeIcons.ttf", "segmdl2.ttf"):
        p = os.path.join(fonts, f)
        if os.path.exists(p):
            return p
    return None


ICON_FONT = _find_icon_font()
_pil_icon_cache = {}
_ctk_icon_cache = {}


def pil_font(name, size):
    for n in (name, "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(n, max(6, int(size)))
        except OSError:
            pass
    return ImageFont.load_default()


def icon_pil(name, size, color=TXT):
    """Icon (Windows Segoe icon font) as an RGBA image."""
    key = (name, size, color)
    if key in _pil_icon_cache:
        return _pil_icon_cache[key]
    img = None
    if ICON_FONT and name in ICON_CHARS:
        font = ImageFont.truetype(ICON_FONT, int(size * 0.92))
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        ch = ICON_CHARS[name]
        b = d.textbbox((0, 0), ch, font=font)
        d.text(((size - (b[2] - b[0])) / 2 - b[0], (size - (b[3] - b[1])) / 2 - b[1]), ch,
               font=font, fill=hex2rgb(color) if isinstance(color, str) else color)
    _pil_icon_cache[key] = img
    return img


def icon(name, size=16, color=TXT):
    """Icon for CustomTkinter widgets."""
    key = (name, size, color)
    if key not in _ctk_icon_cache:
        img = icon_pil(name, size * 3, color)
        _ctk_icon_cache[key] = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size)) if img else None
    return _ctk_icon_cache[key]


def draw_app_icon(s=256):
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    c1, c2 = hex2rgb("#4f8ff7"), hex2rgb("#1d4ed8")
    for y in range(s):
        t = y / (s - 1)
        gd.line([(0, y), (s, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)) + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.23), fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((s * .15, s * .31, s * .64, s * .69), radius=int(s * .08), fill="white")
    d.polygon([(s * .67, s * .45), (s * .86, s * .33), (s * .86, s * .67), (s * .67, s * .55)], fill="white")
    d.ellipse((s * .23, s * .40, s * .35, s * .52), fill=hex2rgb(RED))
    return img


def ensure_app_icon(path=APP_ICO):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        draw_app_icon(256).save(path, format="ICO",
                                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        return path
    except Exception:
        return None


def fit_image(frame, w, h, interp_up=cv2.INTER_LINEAR):
    """Resize a BGR frame to fit w x h keeping the aspect ratio. Returns an RGB numpy array."""
    fh, fw = frame.shape[:2]
    s = min(w / fw, h / fh)
    nw, nh = max(1, int(fw * s)), max(1, int(fh * s))
    if (nw, nh) == (fw, fh):
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    # INTER_AREA is the best for strong reductions but 7 times slower: linear is as good down to half size
    interp = interp_up if s >= 1 else cv2.INTER_LINEAR if s >= 0.5 else cv2.INTER_AREA
    return cv2.cvtColor(cv2.resize(frame, (nw, nh), interpolation=interp), cv2.COLOR_BGR2RGB)
