"""Troca a capa genérica das matérias publicadas pela imagem de divulgação da fonte.

Roda no GitHub Actions (precisa de internet). Para cada matéria publicada,
procura o og:image das fontes, das mais oficiais para as menos, e usa a
primeira que baixar com 800px de largura ou mais. Sem nenhuma, mantém a capa
própria. Imagem de fonte já aplicada não é refeita.
"""
from scripts.engine import images, verify
from scripts.engine.config import load
from scripts.engine.store import load_posts, save_post

OFICIAIS = ("microsoft", "sony", "take-two", "nintendo", "ea", "ubisoft", "valve")

cfg = load()
trocadas = 0
for post in load_posts("pt"):
    if post.get("status") != "published":
        continue
    atual = post.get("image") or {}
    if atual.get("credit", "").startswith("Imagem"):
        continue
    fontes = sorted(post.get("sources", []), key=lambda s: s.get("owner") not in OFICIAIS)
    for fonte in fontes:
        _, url = verify.fetch_page(fonte["url"])
        if not url:
            continue
        oficial = fonte.get("owner") in OFICIAIS
        tentativa = {**post, "image": {**atual, "url": url,
                     "credit": f"Imagem: {fonte['name']}" if oficial
                     else f"Imagem: divulgação, via {fonte['name']}"}}
        achada = images._da_fonte(tentativa)
        if achada:
            post["image"] = achada
            save_post(post)
            trocadas += 1
            print(f"OK   {post['slug']}: {fonte['name']} {url[:90]}")
            break
    else:
        print(f"SEM  {post['slug']}: nenhuma fonte com imagem utilizável")
print(f"{trocadas} capa(s) trocada(s)")
