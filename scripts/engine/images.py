"""Step 6 - cover image, licensed and attributed.

Only Unsplash and Pexels APIs. Never scrape an image off a source article: the
photo in a news story is licensed to that outlet, not to us. Attribution is
stored with the post and rendered under the image.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import requests
from PIL import Image

from .config import ROOT, Config, utm_source
from .util import fingerprint

IMG_DIR = ROOT / "assets" / "img"
MAX_WIDTH = 1200
QUALITY = 82
TIMEOUT = 25


class ImageError(RuntimeError):
    pass


def _unsplash(query: str, orientation: str) -> dict:
    key = os.environ.get("UNSPLASH_ACCESS_KEY", "")
    if not key:
        raise ImageError("UNSPLASH_ACCESS_KEY não configurada")
    response = requests.get(
        "https://api.unsplash.com/search/photos",
        params={"query": query, "orientation": orientation, "per_page": 1, "content_filter": "high"},
        headers={"Authorization": f"Client-ID {key}", "Accept-Version": "v1"},
        timeout=TIMEOUT)
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        raise ImageError(f"Unsplash sem resultado para '{query}'")
    photo = results[0]
    # Unsplash requires pinging the download endpoint when an image is used.
    try:
        requests.get(photo["links"]["download_location"],
                     headers={"Authorization": f"Client-ID {key}"}, timeout=TIMEOUT)
    except requests.RequestException:
        pass
    return {
        "url": photo["urls"]["regular"],
        "provider": "Unsplash",
        "author": photo["user"]["name"],
        "author_url": photo["user"]["links"]["html"] + f"?utm_source={utm_source()}&utm_medium=referral",
        "source_url": photo["links"]["html"],
    }


def _pexels(query: str, orientation: str) -> dict:
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        raise ImageError("PEXELS_API_KEY não configurada")
    response = requests.get(
        "https://api.pexels.com/v1/search",
        params={"query": query, "orientation": orientation, "per_page": 1},
        headers={"Authorization": key}, timeout=TIMEOUT)
    response.raise_for_status()
    photos = response.json().get("photos") or []
    if not photos:
        raise ImageError(f"Pexels sem resultado para '{query}'")
    photo = photos[0]
    return {
        "url": photo["src"]["large"],
        "provider": "Pexels",
        "author": photo["photographer"],
        "author_url": photo["photographer_url"],
        "source_url": photo["url"],
    }


PROVIDERS = {"unsplash": _unsplash, "pexels": _pexels}


def download(url: str, slug: str) -> str:
    """Fetch, downscale, save as JPEG. Returns the site-absolute path."""
    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    image = Image.open(io.BytesIO(response.content)).convert("RGB")
    if image.width > MAX_WIDTH:
        height = round(image.height * MAX_WIDTH / image.width)
        image = image.resize((MAX_WIDTH, height), Image.LANCZOS)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{slug[:40]}-{fingerprint(url)[:8]}.jpg"
    image.save(IMG_DIR / name, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return f"/assets/img/{name}"


def query_ladder(post: dict, cfg: Config) -> list[str]:
    """Buscas da mais específica para a mais genérica.

    Um banco de imagens não tem foto de "server room data breach cybersecurity
    abstract technology abstract" - e foi assim que três matérias boas caíram na
    fila no primeiro dia. Vale mais uma imagem genérica e honesta do que matéria
    parada. A última tentativa é sempre um termo amplo do nicho, que existe.
    """
    base = (post.get("image", {}).get("query") or "").strip()
    suffix = (cfg.get("images.query_suffix") or "").strip()
    words = base.split()
    generic = cfg.localized("niche.term", "en") or "technology"

    tentativas = [
        f"{base} {suffix}".strip(),
        base,
        " ".join(words[:3]),
        " ".join(words[:2]),
        generic,
    ]
    vistas, ladder = set(), []
    for q in tentativas:
        q = " ".join(q.split())
        if q and q.lower() not in vistas:
            vistas.add(q.lower())
            ladder.append(q)
    return ladder


def _da_fonte(post: dict) -> dict | None:
    """Imagem oficial de divulgação (og:image da fonte), recortada em 16:9.

    A redação copia a URL do campo `image` da fonte no briefing para
    `post.image.url`. Se não abrir, for pequena ou não for imagem, devolve
    None e o chamador cai na capa própria.
    """
    img = post.get("image") or {}
    url = (img.get("url") or "").strip()
    if not url:
        return None
    try:
        resp = requests.get(url, headers={"User-Agent": "PixelzadaBot/1.0"}, timeout=TIMEOUT)
        resp.raise_for_status()
        im = Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception:
        return None
    if im.width < 800:
        return None
    im, foco = recortar(im, 16 / 9)
    im = im.resize((MAX_WIDTH, round(MAX_WIDTH * 9 / 16)), Image.LANCZOS)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    # o recorte entra no nome: capa recortada de novo ganha arquivo novo e não
    # fica presa no cache do navegador
    nome = f"{post['slug'][:40]}-{fingerprint(url + '|r2|' + (foco or ''))[:8]}.jpg"
    im.save(IMG_DIR / nome, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    achada = {**img, "path": f"/assets/img/{nome}",
              "credit": (img.get("credit") or "Imagem: divulgação").strip(),
              "source_url": img.get("source_url", "")}
    achada.pop("foco", None)
    if foco:
        achada["foco"] = foco
    return achada


def recortar(im: Image.Image, alvo: float) -> tuple[Image.Image, str | None]:
    """Recorta `im` na proporção `alvo` (largura/altura) sem cortar rosto.

    Com rosto, a janela é posta sobre as cabeças (inteiras, com testa e queixo)
    e devolve também o foco delas na imagem recortada, para o CSS das
    miniaturas usar em object-position. Se as cabeças não cabem na janela
    (rosto em close numa foto em pé), a foto entra inteira na altura das
    cabeças sobre um fundo desfocado dela mesma, como nos Reels. Sem rosto,
    foto alta perde mais embaixo do que em cima (cabeça costuma estar no alto)
    e foto larga perde igual dos dois lados.
    """
    from PIL import ImageFilter, ImageEnhance

    from . import rosto

    caixas = rosto.rostos(im)
    area = rosto.area_das_cabecas(caixas)
    W, H = im.size
    if W / H > alvo:                                   # larga demais: corta dos lados
        jw, jh = round(H * alvo), H
    else:                                              # alta demais: corta embaixo e em cima
        jw, jh = W, round(W / alvo)

    def cabe(a):
        return a[2] - a[0] <= jw and a[3] - a[1] <= jh

    if area and not cabe(area):                        # todos não cabem: fica o rosto principal
        area = rosto.area_das_cabecas([max(caixas, key=lambda c: c[2] * c[3])])
    if area and not cabe(area):
        # não cabe: fundo desfocado + o trecho das cabeças inteiro por cima
        folga = round(0.08 * (area[3] - area[1]))
        if jw == W:                                    # foto em pé: faixa inteira na altura das cabeças
            trecho = im.crop((0, max(0, area[1] - folga), W, min(H, area[3] + folga)))
        else:                                          # foto deitada: coluna inteira na largura delas
            trecho = im.crop((max(0, area[0] - folga), 0, min(W, area[2] + folga), H))
        fx, fy = (W - jw) // 2, round((H - jh) * 0.15)
        fundo = im.crop((fx, fy, fx + jw, fy + jh)).filter(ImageFilter.GaussianBlur(max(jw, jh) / 30))
        fundo = ImageEnhance.Brightness(fundo).enhance(0.55)
        k = min(jw / trecho.width, jh / trecho.height)
        trecho = trecho.resize((max(1, round(trecho.width * k)), max(1, round(trecho.height * k))), Image.LANCZOS)
        fundo.paste(trecho, ((jw - trecho.width) // 2, (jh - trecho.height) // 2))
        return fundo, "50% 50%"

    if jw < W:
        esq = (W - jw) // 2
        if area:
            esq = round((area[0] + area[2]) / 2 - jw / 2)
            esq = min(max(esq, area[2] - jw), area[0])  # nenhuma cabeça pela metade
        esq = min(max(0, esq), W - jw)
        caixa = (esq, 0, esq + jw, H)
    else:
        topo = round((H - jh) * 0.15)
        if area:
            topo = round((area[1] + area[3]) / 2 - jh * 0.42)  # cabeças um pouco acima do meio
            topo = min(max(topo, area[3] - jh), area[1])
        topo = min(max(0, topo), H - jh)
        caixa = (0, topo, W, topo + jh)
    recorte = im.crop(caixa)
    foco = None
    if area:
        cx = ((area[0] + area[2]) / 2 - caixa[0]) / (caixa[2] - caixa[0])
        cy = ((area[1] + area[3]) / 2 - caixa[1]) / (caixa[3] - caixa[1])
        foco = f"{min(100, max(0, round(cx * 100)))}% {min(100, max(0, round(cy * 100)))}%"
    return recorte, foco


def attach(post: dict, cfg: Config) -> dict:
    """Find, download and attach a cover image. Raises ImageError if none can be had."""
    provider = cfg.get("images.provider", "none")
    if provider == "none":
        return post
    if provider in ("cartao", "fonte"):
        from . import capa
        if provider == "fonte":
            achada = _da_fonte(post)
            if achada:
                post["image"] = achada
                return post
        # Sem imagem utilizável da fonte, a matéria sai com a capa própria.
        post["image"] = capa.gerar(post, cfg)
        return post

    orientation = cfg.get("images.orientation", "landscape")
    errors = []
    for name in [provider, cfg.get("images.fallback_provider")]:
        if not name or name not in PROVIDERS:
            continue
        found = None
        for query in query_ladder(post, cfg):
            try:
                found = PROVIDERS[name](query, orientation)
                break
            except (ImageError, requests.RequestException) as exc:
                errors.append(f"{name} '{query}': {exc}")
        if found is None:
            continue
        try:
            post["image"] = {
                **post.get("image", {}),
                "path": download(found["url"], post["slug"]),
                "credit": f"{found['author']} / {found['provider']}",
                "author": found["author"],
                "author_url": found["author_url"],
                "provider": found["provider"],
                "source_url": found["source_url"],
            }
            return post
        except (ImageError, requests.RequestException, OSError) as exc:
            errors.append(f"{name}: {exc}")
    raise ImageError("; ".join(errors) or "nenhum provedor de imagem configurado")
