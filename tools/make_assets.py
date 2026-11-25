"""Genera el logo y el icono de NODORA (diseño original). Requiere Pillow."""
from PIL import Image, ImageDraw, ImageFont
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "assets")
os.makedirs(OUT, exist_ok=True)
CREAM, INK, YEL, GREEN = (243, 240, 234), (30, 30, 30), (255, 194, 46), (47, 125, 82)


def icon(size=512):
    s = size
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=INK)
    # tres nodos conectados formando una "N"
    pts = [(0.28, 0.72), (0.28, 0.28), (0.72, 0.72), (0.72, 0.28)]
    P = [(int(x * s), int(y * s)) for x, y in pts]
    for a, b in zip(P, P[1:]):
        d.line([a, b], fill=CREAM, width=int(s * 0.07), joint="curve")
    for i, p in enumerate(P):
        r = int(s * 0.075)
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=YEL if i == 3 else CREAM)
    return im


def font(size):
    for f in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def logo():
    W, H = 1100, 300
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ic = icon(220)
    im.paste(ic, (20, 40), ic)
    d = ImageDraw.Draw(im)
    d.text((270, 55), "NODORA", font=font(120), fill=INK)
    d.ellipse([872, 70, 908, 106], fill=YEL)
    d.text((276, 200), "REMOTE SYSTEM MANAGEMENT", font=font(30), fill=(123, 123, 123))
    return im


if __name__ == "__main__":
    i = icon(512)
    i.save(os.path.join(OUT, "nodora.png"))
    i.save(os.path.join(OUT, "nodora.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    logo().save(os.path.join(OUT, "nodora_logo.png"))
    print("assets generados en", os.path.abspath(OUT))
