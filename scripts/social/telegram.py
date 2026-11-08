"""Robô do Telegram da Pixelzada: o jeito rápido do Diego mandar referências.

No Instagram, o Diego toca em Compartilhar > Telegram > bot da Pixelzada. A cada
10 minutos o GitHub Actions (.github/workflows/telegram.yml) lê as mensagens
novas do bot e aplica a regra combinada em 08/11:

  link de PERFIL do Instagram   entra como concorrente no motor de pesquisa
                                (social/pesquisa/config.yaml)
  link de VÍDEO (Reel/post)     baixa e põe em social/reels/entrada/; o job
                                "montar" põe na identidade e agenda na fila
  ARQUIVO de vídeo              mesmo caminho do link, sem depender da API
                                (é a saída quando o link vem "sem arquivo")

O bot responde em cada mensagem dizendo o que fez. Depois da montagem,
`avisar` conta o dia e o horário em que o Reel entrou na fila.

Só o dono fala com o bot: a primeira conversa que mandar /start vira a do dono
(o número dela fica em social/telegram/estado.json; sem o token ele não serve
para nada). Mensagens de outras conversas são ignoradas.

    python -m scripts.social.telegram ler       processa as mensagens novas
    python -m scripts.social.telegram avisar    conta o horário dos Reels já agendados

Chave: secret TELEGRAM_TOKEN_PIXELZADA (o token que o BotFather entrega).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from . import pesquisa as P

ROOT = P.ROOT
TZ = P.TZ
SEGREDO = "TELEGRAM_TOKEN_PIXELZADA"
ESTADO = ROOT / "social" / "telegram" / "estado.json"
FILA = ROOT / "social" / "reels" / "fila.json"
LIMITE_BOT = 20 * 1024 * 1024   # o bot só baixa arquivos de até 20 MB
RESERVADOS = {"reel", "reels", "p", "tv", "stories", "explore", "accounts", "direct", "about", "legal",
              "developer", "web", "s", "share", "highlights"}
URL = re.compile(r"https?://\S+")
PERFIL = re.compile(r"instagram\.com/([A-Za-z0-9_.]{1,30})/?(?:[?#]|$)")

AJUDA = ("Oi! Aqui é o robô da Pixelzada. Pode mandar:\n"
         "• link de um Reel ou post do Instagram: eu baixo, monto na identidade e ponho na fila\n"
         "• link de um perfil: entra como concorrente no motor de pesquisa\n"
         "• o arquivo do vídeo: vira Reel direto (use quando eu disser \"sem arquivo\")\n\n"
         "No Instagram é só tocar em Compartilhar > Telegram > Pixelzada. Respondo em até uns 15 minutos.")


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
class Bot:
    def __init__(self, token: str):
        self._token = token

    def chamar(self, metodo: str, **dados) -> dict:
        req = urllib.request.Request(f"https://api.telegram.org/bot{self._token}/{metodo}",
                                     data=json.dumps(dados).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read())
        except urllib.error.HTTPError as e:
            # nunca imprimir a URL: ela carrega o token
            raise RuntimeError(f"Telegram {metodo}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"Telegram {metodo}: sem resposta ({e.reason})") from None
        if not resp.get("ok"):
            raise RuntimeError(f"Telegram {metodo}: {resp.get('description')}")
        return resp["result"]

    def responder(self, chat: int, texto: str, msg_id: int | None = None) -> None:
        dados = {"chat_id": chat, "text": texto, "disable_web_page_preview": True}
        if msg_id:
            dados["reply_parameters"] = {"message_id": msg_id, "allow_sending_without_reply": True}
        try:
            self.chamar("sendMessage", **dados)
        except RuntimeError as e:
            print(f"  não consegui responder: {e}")

    def baixar(self, file_id: str, destino: Path) -> None:
        caminho = self.chamar("getFile", file_id=file_id)["file_path"]
        with urllib.request.urlopen(f"https://api.telegram.org/file/bot{self._token}/{caminho}", timeout=180) as r:
            destino.write_bytes(r.read())


def carregar_estado() -> dict:
    if ESTADO.exists():
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    return {"offset": 0, "dono": None, "aguardando": []}


def salvar_estado(estado: dict) -> None:
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Regras
# ---------------------------------------------------------------------------
def classificar(url: str) -> tuple[str, str | None]:
    """('video', código) | ('perfil', usuário) | ('outro', None)."""
    if "instagram.com" not in url:
        return "outro", None
    m = P.CODIGO_LINK.search(url)
    if m:
        return "video", m.group(1)
    m = PERFIL.search(url)
    if m and m.group(1).lower() not in RESERVADOS:
        return "perfil", m.group(1).lower()
    return "outro", None


def adicionar_concorrente(cfg: dict, perfil: str, conexao: tuple[str, str] | None) -> str:
    """Põe o perfil no fim da lista de concorrentes do config.yaml (texto, para manter os comentários)."""
    if any(c["perfil"].lower() == perfil for c in cfg["concorrentes"]):
        return f"@{perfil} já está entre os concorrentes do motor."
    tema, extra = "games", ""
    if conexao:
        try:
            dado = P.ler_perfil({**cfg, "posts_por_perfil": 12}, conexao[0], conexao[1], perfil)
            legendas = " ".join(p.get("caption") or "" for p in dado["posts"])
            tema = P.tema_de(cfg, legendas, "games")
            extra = f" ({P.fmt(dado['seguidores'])} seguidores, {len(dado['posts'])} posts lidos)"
        except P.ApiError as e:
            print(f"  @{perfil}: {str(e)[:200]}")
            return (f"Não consegui ler @{perfil} pela API do Instagram. Ela só enxerga perfis "
                    "profissionais (empresa ou criador) e públicos, então não adicionei.")
    arq = Path(cfg["_arquivo"])
    texto = arq.read_text(encoding="utf-8").rstrip("\n")
    hoje = datetime.now(TZ).strftime("%d/%m")
    texto += f"\n  - {{perfil: {perfil}, tema: {tema}}}  # Telegram {hoje}\n"
    arq.write_text(texto, encoding="utf-8")
    cfg["concorrentes"].append({"perfil": perfil, "tema": tema})
    nome = cfg["temas"].get(tema, {}).get("nome", tema)
    return f"Pronto: @{perfil} entrou como concorrente{extra}. Tema: {nome}. Já vale na próxima coleta."


def video_por_link(cfg: dict, url: str, conexao: tuple[str, str] | None, estado: dict) -> str:
    if not conexao:
        return "A chave da pesquisa (META_TOKEN_PIXELZADA) não está cadastrada, então não consigo baixar pelo link."
    final, c = P.baixar_link(cfg, url, *conexao)
    if not final:
        return ("Esse vídeo veio SEM ARQUIVO pela API do Instagram (música licenciada ou download "
                "desligado). Me manda o próprio vídeo aqui: no Instagram toque nos 3 pontinhos > Baixar "
                "(ou grave a tela) e envie o arquivo nesta conversa.")
    estado["aguardando"].append({"link": c["link"], "chat": estado["_chat"], "msg": estado["_msg"]})
    return (f"Baixei o vídeo de @{c['perfil']} ({c['jogo']}). Vou montar na identidade e pôr na fila; "
            "te aviso aqui o dia e o horário.")


def video_por_arquivo(cfg: dict, bot: Bot, msg: dict, conexao: tuple[str, str] | None, estado: dict) -> str:
    arquivo = msg.get("video") or msg.get("document") or {}
    if msg.get("document") and not str(arquivo.get("mime_type", "")).startswith("video/"):
        return "Esse arquivo não é vídeo. Mande o vídeo (mp4) ou o link do Reel."
    if (arquivo.get("file_size") or 0) > LIMITE_BOT:
        return ("O vídeo passou de 20 MB, que é o limite que o robô consegue baixar do Telegram. "
                "Mande de novo como vídeo normal (não como arquivo), que o Telegram comprime.")
    legenda = msg.get("caption") or ""
    links = URL.findall(legenda)
    c, cache = None, {}
    if links and conexao:  # vídeo com o link na legenda: aproveita o dono e a legenda original
        achado = P.dados_do_link(cfg, links[0], *conexao)
        if achado:
            c, cache = achado
    unico = arquivo["file_unique_id"]
    if not c:
        tema = P.tema_de(cfg, legenda, "games")
        c = {"id": f"tg-{unico}", "perfil": "diego", "link": f"telegram:{unico}", "tema": tema,
             "jogo": cfg["temas"][tema]["nome"], "legenda": legenda[:160], "legenda_completa": legenda[:700]}
    destino = cfg["_entrada"] / datetime.now(TZ).date().isoformat()
    destino.mkdir(parents=True, exist_ok=True)
    nome = destino / f"00-link-tg-{re.sub(r'[^a-z0-9]+', '', unico.lower())[:16]}.mp4"
    bot.baixar(arquivo["file_id"], nome)
    info = {k: c.get(k) for k in ("perfil", "link", "jogo", "tema", "legenda", "legenda_completa")}
    info.update({"numero": 0, "horario_sugerido": None, "via": "Telegram"})
    nome.with_suffix(".json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ja = P.usados(cfg)
    ja.update({c["id"], c["link"]})
    P.salvar_usados(cfg, ja)
    print(f"  arquivo salvo: {nome.parent.name}/{nome.name} ({nome.stat().st_size // 1024} KB)")
    estado["aguardando"].append({"link": c["link"], "chat": estado["_chat"], "msg": estado["_msg"]})
    return f"Recebi o vídeo ({c['jogo']}). Vou montar na identidade e pôr na fila; te aviso aqui o dia e o horário."


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------
def ler(cfg: dict) -> int:
    token = os.environ.get(SEGREDO, "").strip()
    if not token:
        print(f"o secret {SEGREDO} não está cadastrado; nada a fazer")
        return 0
    bot, estado = Bot(token), carregar_estado()
    updates = bot.chamar("getUpdates", offset=estado["offset"], timeout=0,
                         allowed_updates=["message"])
    print(f"{len(updates)} mensagem(ns) nova(s)")
    conexao = None
    if os.environ.get(cfg["segredo"], "").strip():
        try:
            conexao = P.conta(cfg)
        except P.ApiError as e:
            print(f"chave da pesquisa não funcionou: {e}")
    for up in updates:
        estado["offset"] = up["update_id"] + 1
        msg = up.get("message") or {}
        chat = (msg.get("chat") or {}).get("id")
        if not chat:
            continue
        texto = msg.get("text") or msg.get("caption") or ""
        if estado["dono"] is None:
            if texto.strip().startswith("/start"):
                estado["dono"] = chat
                print("  dono do bot registrado")
                bot.responder(chat, AJUDA)
            continue
        if chat != estado["dono"]:
            print("  mensagem de outra conversa: ignorada")
            continue
        estado["_chat"], estado["_msg"] = chat, msg.get("message_id")
        respostas = []
        try:
            if msg.get("video") or msg.get("document"):
                respostas.append(video_por_arquivo(cfg, bot, msg, conexao, estado))
            else:
                urls = URL.findall(texto)
                for url in urls[:5]:
                    tipo, valor = classificar(url)
                    print(f"  {tipo}: {valor or url[:60]}")
                    if tipo == "video":
                        respostas.append(video_por_link(cfg, url, conexao, estado))
                    elif tipo == "perfil":
                        respostas.append(adicionar_concorrente(cfg, valor, conexao))
                    else:
                        respostas.append("Por enquanto eu entendo só links do Instagram. De outro site "
                                         "(TikTok, YouTube, X), mande o arquivo do vídeo aqui.")
                if not urls:
                    respostas.append(AJUDA)
        except Exception as e:  # uma mensagem ruim não pode travar as outras
            print(f"  erro: {e}")
            respostas.append("Deu um erro aqui e não consegui processar essa mensagem. "
                             "O Claude vai olhar; se for urgente, cola o link na conversa com ele.")
        for r in respostas:
            bot.responder(chat, r, msg.get("message_id"))
    estado.pop("_chat", None)
    estado.pop("_msg", None)
    salvar_estado(estado)
    if updates:  # confirma para o Telegram não entregar de novo
        bot.chamar("getUpdates", offset=estado["offset"], timeout=0, limit=1)
    return 0


def avisar(cfg: dict) -> int:
    """Conta no Telegram o dia e a hora dos Reels que já entraram na fila."""
    token = os.environ.get(SEGREDO, "").strip()
    estado = carregar_estado()
    if not token or not estado["aguardando"]:
        return 0
    fila = json.loads(FILA.read_text(encoding="utf-8")) if FILA.exists() else []
    fila = fila.get("itens", fila) if isinstance(fila, dict) else fila
    por_link = {(i.get("origem") or {}).get("link"): i for i in fila if i.get("status") == "agendado"}
    bot, resta = Bot(token), []
    for a in estado["aguardando"]:
        item = por_link.get(a["link"])
        if not item:
            resta.append(a)
            continue
        d = datetime.fromisoformat(item["data"])
        bot.responder(a["chat"], f"Montado e na fila: sai {d.strftime('%d/%m')} às {item['horario']} "
                                 f"(estilo {item.get('estilo', '?')}).", a.get("msg"))
    estado["aguardando"] = resta
    salvar_estado(estado)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(P.CONFIG_PADRAO))
    ap.add_argument("cmd", choices=["ler", "avisar"])
    args = ap.parse_args(argv)
    cfg = P.carregar_config(Path(args.config))
    cfg["_arquivo"] = args.config
    return ler(cfg) if args.cmd == "ler" else avisar(cfg)


if __name__ == "__main__":
    sys.exit(main())
