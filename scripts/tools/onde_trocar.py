"""Lista onde a marca antiga ainda aparece, para replicar o sistema em outra marca.

Só lê, não muda nada. Use no repositório NOVO, depois de copiar os arquivos da
Pixelzada, até a lista ficar vazia (ou só com o que for de propósito):

    python scripts/tools/onde_trocar.py                 # procura "pixelzada"
    python scripts/tools/onde_trocar.py pixelzada gta   # várias palavras

Pula conteúdo publicado e estado (pt/, content/, data/, vídeos, coletas), que
no repositório novo começa vazio. Guia: docs/replicar/GUIA-REPLICAR.md.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PULAR = {".git", "node_modules", "__pycache__", "pt", "content", "data", "docs"}
PULAR_CAMINHO = ("social/reels/videos", "social/reels/entrada", "social/pesquisa/coletas",
                 "social/pesquisa/listas", "social/pautas", "social/prontas", "social/publicar")
TEXTO = {".py", ".js", ".yml", ".yaml", ".md", ".json", ".html", ".j2", ".css", ".txt",
         ".xml", ".svg", ".webmanifest", ".toml"}


def arquivos():
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT)
        if not p.is_file() or p.suffix.lower() not in TEXTO:
            continue
        if rel.parts[0] in PULAR or any(part in PULAR for part in rel.parts):
            continue
        if any(rel.as_posix().startswith(c) for c in PULAR_CAMINHO):
            continue
        yield p, rel


def main(palavras: list[str]) -> int:
    palavras = [w.lower() for w in palavras] or ["pixelzada"]
    achados: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for p, rel in arquivos():
        try:
            linhas = p.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for n, linha in enumerate(linhas, 1):
            baixa = linha.lower()
            if any(w in baixa for w in palavras):
                achados[rel.as_posix()].append((n, linha.strip()[:120]))
    nomes = [p.name for p, _ in arquivos()]
    com_nome = sorted({n for n in nomes if any(w in n.lower() for w in palavras)})
    total = sum(len(v) for v in achados.values())
    print(f"Procurando: {', '.join(palavras)}\n")
    for arq in sorted(achados):
        print(f"{arq}  ({len(achados[arq])})")
        for n, linha in achados[arq][:8]:
            print(f"    {n}: {linha}")
        if len(achados[arq]) > 8:
            print(f"    ... mais {len(achados[arq]) - 8}")
    if com_nome:
        print("\nArquivos com a marca no NOME (renomear):")
        for n in com_nome:
            print(f"    {n}")
    print(f"\n{total} linha(s) em {len(achados)} arquivo(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
