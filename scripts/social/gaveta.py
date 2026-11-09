"""Página "Gaveta de Reels" do Diego: o que ainda vai sair, sem os Reels já publicados.

Lê social/reels/fila.json, escreve o HTML da página e imprime um resumo para a rotina
diária conferir o que realmente saiu (campo `publicado` com media_id, gravado pelo robô).

    python -m scripts.social.gaveta [saida.html]

Linhas do resumo que a rotina lê:
    ATRASADO <data> <hora> <slug>   horário que já fechou (janela de 110 min) e o Reel não saiu
    GAVETA_BAIXA <n>                menos de 2 dias de vídeos (menos de 12)
"""
from __future__ import annotations

import html
import sys
from datetime import date, datetime, timedelta

from . import pauta as P
from .reels import DEPOIS, carregar, horarios

# Grade de amanhã (15 Reels/dia de 10 a 15/11, 25/dia desde 16/11).
HORARIOS = horarios(datetime.now(P.TZ).date() + timedelta(days=1))
POR_DIA = len(HORARIOS)

SEMANA = POR_DIA * 7
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
LIMITE_BAIXA = POR_DIA * 2


GRADE_TXT = ("Aquecimento para o GTA 6: até 09/11 são 6 Reels por dia; de 10 a 15/11, 15 por dia "
             "(8h30 às 22h30, de hora em hora); a partir de 16/11, 25 por dia (9h15 às 21h15, de 30 em 30 minutos).")


def _h(txt: str) -> str:
    return txt.replace(":00", "h").replace(":", "h")


def _titulo(item: dict) -> str:
    return (item.get("legenda") or item["slug"]).split("\n\n")[0].strip()


def _item(hora: str, titulo: str, pequeno: str, tag: str = "Agendado", vazio: bool = False) -> str:
    cls = "item vazio" if vazio else "item"
    return (f'      <div class="{cls}"><span class="hora">{hora}</span><div><strong>{html.escape(titulo)}</strong>'
            f'<small>{html.escape(pequeno)}</small></div><span class="tag">{tag}</span></div>\n')


def _inicio(item: dict) -> datetime:
    return datetime.fromisoformat(f"{item['data']}T{item['horario']}:00").replace(tzinfo=P.TZ)


def pagina(agora: datetime | None = None) -> tuple[str, list[str]]:
    agora = agora or datetime.now(P.TZ)
    fila = carregar()
    hoje = agora.date()
    pend = sorted((i for i in fila if i.get("status") != "publicado"), key=lambda i: (i["data"], i["horario"]))
    saiu_hoje = [i for i in fila if i.get("status") == "publicado" and i["data"] == hoje.isoformat()]
    avisos: list[str] = []
    for i in pend:
        if agora > _inicio(i) + DEPOIS:
            avisos.append(f"ATRASADO {i['data']} {i['horario']} {i['slug']}")
    n = len(pend)
    falta = max(0, SEMANA - n)
    if n < LIMITE_BAIXA:
        avisos.append(f"GAVETA_BAIXA {n}")

    por_dia: dict[str, list[dict]] = {}
    for i in pend:
        por_dia.setdefault(i["data"], []).append(i)
    fila_html = '  <section>\n    <h2>Fila de publicação</h2>\n'
    for dia, itens in por_dia.items():
        d = date.fromisoformat(dia)
        if d == hoje:
            resumo = f"{len(saiu_hoje)} já saíram, {len(itens)} na fila"
        else:
            resumo = f"{len(itens)} de {len(horarios(d))}"
        fila_html += f'    <div class="dia">\n      <header>{DIAS[d.weekday()]}, {d.day:02d}/{d.month:02d} <span>{resumo}</span></header>\n'
        for i in itens:
            atrasado = agora > _inicio(i) + DEPOIS
            fila_html += _item(i["horario"], _titulo(i), i.get("estilo", ""),
                               "Perdeu a hora" if atrasado else "Agendado", vazio=atrasado)
        fila_html += "    </div>\n"
    if pend:
        u = pend[-1]
        ud = date.fromisoformat(u["data"])
        fim = f"{ud.day:02d}/{ud.month:02d} às {_h(u['horario'])}"
        ult_num, ult_txt = f"{ud.day}/{ud.month}", f"até {_h(u['horario'])}"
        duracao = f"até {fim}"
        fila_html += (f'    <div class="dia vazio">\n      <header>Depois de {DIAS[ud.weekday()].lower()}, {fim} <span>vazio</span></header>\n'
                      + _item("—", "Sem vídeos", f"A gaveta acaba em {fim}", "Vazio", vazio=True) + "    </div>\n")
    else:
        ult_num, ult_txt, duracao = "—", "sem vídeos", "nenhum dia"
        fila_html += '    <div class="dia vazio">\n' + _item("—", "Gaveta vazia", "Mande vídeos novos", "Vazio", vazio=True) + "    </div>\n"
    fila_html += "  </section>"
    horas = ", ".join(_h(h) for h in HORARIOS[:-1]) + f" e {_h(HORARIOS[-1])}"
    quando = f"{agora.day:02d}/{agora.month:02d}, {agora.hour}h{agora.minute:02d}"
    dias_restam = round(n / POR_DIA) if n else 0
    out = TEMPLATE
    out = out.replace("@@SUB@@", f"Vídeos aprovados esperando a hora de sair no @pixelzada.br. Posição em {quando}. "
                      f"{GRADE_TXT} Os Reels já publicados saem da lista e a página é atualizada todo dia à noite.")
    out = out.replace("@@N@@", str(n)).replace("@@ULT_NUM@@", ult_num).replace("@@ULT_TXT@@", ult_txt)
    out = out.replace("@@FALTA@@", str(falta)).replace("@@SEMANA@@", str(SEMANA)).replace("@@FILA@@", fila_html)
    out = out.replace("@@POR_DIA@@", str(POR_DIA)).replace("@@HORAS@@", horas).replace("@@LIMITE@@", str(LIMITE_BAIXA))
    out = out.replace("@@DURA@@", f"Hoje a gaveta dura cerca de {dias_restam} dia(s), {duracao}.")
    return out, avisos


def main() -> int:
    destino = sys.argv[1] if len(sys.argv) > 1 else None
    out, avisos = pagina()
    if destino:
        with open(destino, "w", encoding="utf-8") as f:
            f.write(out)
    fila = carregar()
    hoje = datetime.now(P.TZ).date().isoformat()
    pend = [i for i in fila if i.get("status") != "publicado"]
    print(f"na_gaveta {len(pend)}  faltam_para_semana {max(0, SEMANA - len(pend))}")
    for i in fila:
        if i.get("status") == "publicado" and i["data"] == hoje:
            p = i.get("publicado", {})
            print(f"PUBLICADO_HOJE {i['horario']} {i['slug']} {p.get('media_id', '?')} {p.get('permalink', '')}")
    for a in avisos:
        print(a)
    return 0


TEMPLATE = """<title>Gaveta de Reels</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@400;600;800&display=swap">
<style>
/* Layout: resumo em 3 números no topo, depois a fila dia a dia e a conta de quantos vídeos mandar. */
:root{--bg:#F6F5F9;--surface:#FFFFFF;--fg:#17151F;--muted:#5E5A70;--line:#DCD9E6;--accent:#4B6A00;--accent-bg:#C6FF1A;--accent-fg:#0B0A10;--warn:#B3470A;--ok:#1D7A3E;
--display:Anton,Impact,sans-serif;--body:Archivo,system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0B0A10;--surface:#17151F;--fg:#F3F1F9;--muted:#A7A3B5;--line:#2A2733;--accent:#C6FF1A;--warn:#FF8A1F;--ok:#5CE08A;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0B0A10;--surface:#17151F;--fg:#F3F1F9;--muted:#A7A3B5;--line:#2A2733;--accent:#C6FF1A;--warn:#FF8A1F;--ok:#5CE08A;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:400 16px/1.5 var(--body);padding-inline:16px;padding-block:28px}
main{max-width:760px;margin:0 auto;display:flex;flex-direction:column;gap:28px}
h1{font:400 clamp(34px,8vw,52px)/1 var(--display);text-transform:uppercase;letter-spacing:.5px;text-wrap:balance}
h1 span{background:var(--accent-bg);color:var(--accent-fg);padding:0 .12em}
h2{font:800 13px/1 var(--body);text-transform:uppercase;letter-spacing:.12em;color:var(--muted);margin-bottom:12px}
p{max-width:65ch}
.sub{color:var(--muted);margin-top:10px}
.nums{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.num{background:var(--surface);border:1px solid var(--line);padding:16px}
.num b{display:block;font:400 44px/1 var(--display);color:var(--accent)}
.num small{color:var(--muted);font-size:14px}
.dia{background:var(--surface);border:1px solid var(--line);margin-bottom:12px}
.dia header{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:12px 16px;border-bottom:1px solid var(--line);font-weight:800}
.dia header span{color:var(--muted);font-weight:600}
.item{display:grid;grid-template-columns:64px minmax(0,1fr) auto;gap:12px;align-items:center;padding:12px 16px;border-top:1px solid var(--line)}
.item:first-of-type{border-top:0}
.hora{font:600 15px/1 var(--body);font-variant-numeric:tabular-nums}
.item strong{display:block;overflow-wrap:anywhere}
.item small{color:var(--muted)}
.tag{font:800 12px/1 var(--body);text-transform:uppercase;letter-spacing:.06em;padding:6px 8px;border:1px solid var(--ok);color:var(--ok);white-space:nowrap}
.vazio{border-style:dashed}
.vazio .hora,.vazio strong{color:var(--muted)}
.vazio .tag{border-color:var(--warn);color:var(--warn)}
.conta{background:var(--surface);border:1px solid var(--line);padding:16px 18px}
.conta ul{padding-left:20px;display:flex;flex-direction:column;gap:6px;margin-top:8px}
.rodape{color:var(--muted);font-size:14px}
</style>
<main>
  <div>
    <h1>Gaveta de <span>Reels</span></h1>
    <p class="sub">@@SUB@@</p>
  </div>

  <section class="nums" aria-label="Resumo">
    <div class="num"><b>@@N@@</b><small>vídeos na gaveta</small></div>
    <div class="num"><b>@@ULT_NUM@@</b><small>último dia coberto (@@ULT_TXT@@)</small></div>
    <div class="num"><b>@@FALTA@@</b><small>faltam para a gaveta ter uma semana (@@SEMANA@@)</small></div>
  </section>

@@FILA@@

  <section class="conta">
    <h2>Quantos vídeos mandar</h2>
    <p>O ritmo de amanhã é de @@POR_DIA@@ Reels por dia, @@SEMANA@@ por semana, às @@HORAS@@.</p>
    <ul>
      <li>Para a gaveta ficar com uma semana cheia, faltam <strong>@@FALTA@@ vídeos</strong>.</li>
      <li>Depois disso, mande <strong>@@POR_DIA@@ vídeos por dia</strong> (@@SEMANA@@ por semana) para ela não esvaziar.</li>
      <li>Eu aviso quando restarem menos de 2 dias de vídeos (menos de @@LIMITE@@). @@DURA@@</li>
      <li>Vídeo recebido leva uns minutos para ser montado e entra sozinho no primeiro horário livre.</li>
      <li>Se um Reel perder a hora, ele vai sozinho para o próximo horário livre.</li>
      <li>Perto do lançamento do GTA 6 (19/11) refazemos esse planejamento.</li>
    </ul>
  </section>

  <p class="rodape">Nada sai sem estar nesta fila. Para saber a posição atual, é só perguntar na conversa do projeto.</p>
</main>
"""


if __name__ == "__main__":
    raise SystemExit(main())
