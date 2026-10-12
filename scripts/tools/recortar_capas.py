"""Refaz o recorte das capas publicadas a partir da imagem original da fonte.

Até 12/10/2026 a foto em pé era cortada num ponto fixo e cortava o rosto dos
personagens (Lucia, Jason). Este script baixa de novo a imagem original de
cada matéria publicada (`image.url`), recorta com images.recortar, que acha os
rostos, e troca o arquivo. Capa que não baixar fica como está. Roda no GitHub
Actions (workflow Capas), que tem internet.
"""
from scripts.engine import images
from scripts.engine.config import ROOT
from scripts.engine.store import load_posts, save_post

trocadas = 0
for post in load_posts("pt"):
    if post.get("status") != "published":
        continue
    atual = post.get("image") or {}
    if not (atual.get("url") or "").strip() or not atual.get("path"):
        continue
    nova = images._da_fonte(post)
    if not nova:
        print(f"SEM  {post['slug']}: original não baixou, capa mantida")
        continue
    if nova["path"] == atual["path"] and nova.get("foco") == atual.get("foco"):
        print(f"IGUAL {post['slug']}")
        continue
    velho = ROOT / atual["path"].lstrip("/")
    if nova["path"] != atual["path"] and velho.exists():
        velho.unlink()
    post["image"] = nova
    save_post(post)
    trocadas += 1
    print(f"OK   {post['slug']}: foco {nova.get('foco') or 'sem rosto'}")
print(f"{trocadas} capa(s) recortada(s) de novo")
