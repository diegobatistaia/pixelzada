"""Costura os ladrilhos do mapa de satélite do GTA V (z_x_y.jpg, 256 px) num JPG só, cortado na ilha."""
import hashlib, sys
from pathlib import Path
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
src, z, out = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
n = 2 ** z
vazio = hashlib.md5((src / "empty.jpg").read_bytes()).hexdigest()
cheios = []
for x in range(n):
    for y in range(n):
        f = src / f"{z}_{x}_{y}.jpg"
        if f.exists() and hashlib.md5(f.read_bytes()).hexdigest() != vazio:
            cheios.append((x, y))
xs = [c[0] for c in cheios]; ys = [c[1] for c in cheios]
x0, x1, y0, y1 = min(xs) - 1, max(xs) + 1, min(ys) - 1, max(ys) + 1
print("ladrilhos", len(cheios), "x", x0, x1, "y", y0, y1)
img = Image.new("RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256))
for x in range(x0, x1 + 1):
    for y in range(y0, y1 + 1):
        f = src / f"{z}_{x}_{y}.jpg"
        t = Image.open(f if f.exists() else src / "empty.jpg").convert("RGB")
        img.paste(t, ((x - x0) * 256, (y - y0) * 256))
img.save(out, quality=90)
img.resize((img.width // 8, img.height // 8)).save(out.with_name("mini.jpg"), quality=85)
print(img.size)
