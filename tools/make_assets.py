"""Genera los recursos gráficos de NODORA a partir del logo oficial (assets/nodora_logo_full.png). Requiere Pillow y numpy.

Salidas: nodora_logo.png (símbolo con fondo transparente, para la pantalla de carga), nodora.png y nodora.ico (iconos)."""
import os

import numpy as np
from PIL import Image

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
FULL = os.path.join(OUT, "nodora_logo_full.png")
MARK_BOX = (350, 70, 1180, 545)          # símbolo: «N» + órbita (sin el texto)


def cut_background(im: Image.Image) -> Image.Image:
    """Quita el fondo crema con transparencia suave y limpia el halo de los bordes."""
    a = np.asarray(im.convert("RGB")).astype(np.float64)
    bg = a[2, 2]
    dist = np.sqrt(((a - bg) ** 2).sum(axis=2))
    alpha = np.clip((dist - 10) / 45.0, 0, 1)
    out = np.zeros(a.shape[:2] + (4,))
    safe = np.where(alpha > 0.02, alpha, 1)[..., None]
    out[..., :3] = np.clip((a - (1 - alpha[..., None]) * bg) / safe, 0, 255)
    out[..., 3] = alpha * 255
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def square(im: Image.Image, size: int, pad: float = 0.06) -> Image.Image:
    bbox = im.getbbox()
    im = im.crop(bbox)
    inner = int(size * (1 - 2 * pad))
    im.thumbnail((inner, inner), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)
    return canvas


def main():
    src = Image.open(FULL)
    mark = cut_background(src.crop(MARK_BOX))
    trimmed = mark.crop(mark.getbbox())
    trimmed.save(os.path.join(OUT, "nodora_logo.png"))
    icon = square(mark, 512)
    icon.save(os.path.join(OUT, "nodora.png"))
    icon.save(os.path.join(OUT, "nodora.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Recursos generados en", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
