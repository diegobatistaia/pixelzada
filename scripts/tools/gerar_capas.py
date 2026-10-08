"""Gera a capa própria das matérias publicadas que ainda não têm imagem."""
from scripts.engine import images
from scripts.engine.config import load
from scripts.engine.store import load_posts, save_post

cfg = load()
n = 0
for post in load_posts("pt"):
    if post.get("status") == "published" and not (post.get("image") or {}).get("path"):
        save_post(images.attach(post, cfg))
        n += 1
print(f"{n} capa(s) gerada(s)")
