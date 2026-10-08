#!/usr/bin/env python3
"""Generate the institutional pages AdSense requires, one set per language.

Sobre / Privacidade / Contato / Termos. Written from site.config.yaml so the
domain, e-mail and publisher name stay in one place. Re-run after changing any
of those; the files are plain JSON and can also be edited by hand afterwards.

Run: python scripts/tools/make_pages.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.engine.config import ROOT, load  # noqa: E402
from scripts.engine.util import isoformat, utcnow  # noqa: E402

OUT = ROOT / "content" / "pages"


def p(text):
    return {"type": "p", "text": text, "items": []}


def h2(text):
    return {"type": "h2", "text": text, "items": []}


def ul(items):
    return {"type": "list", "text": "", "items": items}


def pages_for(lang: str, cfg) -> list[dict]:
    name = cfg.get("site.name")
    domain = cfg.get("site.domain")
    email = cfg.get("legal.contact_email")
    niche = cfg.localized("niche.term", lang)
    mail = f'<a href="mailto:{email}">{email}</a>'
    # Artigo do nome da marca em português: "o Cortexplor", "a Pixelzada".
    o = cfg.get("site.article_pt", "o")
    O, do, no = o.capitalize(), {"o": "do", "a": "da"}[o], {"o": "no", "a": "na"}[o]

    if lang == "pt":
        return [
            {"slug": "sobre", "key": "about", "title": f"Sobre {o} {name}",
             "description": f"O que é {o} {name}, como as matérias são produzidas e checadas.",
             "body": [
                 p(cfg.localized("site.about", lang) or
                   f"{O} {name} é um site de notícias dedicado a {niche}."),
                 h2("Como as matérias são produzidas"),
                 p("Nossa produção editorial é assistida por inteligência artificial e opera "
                   "sobre um processo fixo de checagem. O fluxo é o mesmo para toda matéria:"),
                 ul(["Coleta de notícias recentes em fontes jornalísticas estabelecidas;",
                     "Checagem cruzada: um fato só entra no texto se aparecer confirmado em "
                     "pelo menos duas fontes independentes entre si;",
                     "Redação original a partir dos fatos confirmados, sem cópia ou paráfrase "
                     "próxima do texto-fonte;",
                     "Verificação automática de originalidade, estrutura e citação de fontes "
                     "antes da publicação."]),
                 p("Pautas que não passam por todas essas etapas não são publicadas: ficam "
                   "retidas para revisão humana ou são descartadas."),
                 h2("Transparência"),
                 p("Toda matéria lista, ao final, as fontes usadas na apuração. Quando as "
                   "fontes divergem sobre um dado, isso é dito no texto em vez de escondido."),
                 h2("Correções"),
                 p(f"Encontrou um erro? Escreva para {mail} com o link da matéria. "
                   f"Correções relevantes são sinalizadas na própria página."),
             ]},
            {"slug": "privacidade", "key": "privacy", "title": "Política de Privacidade",
             "description": f"Como {o} {name} trata dados de navegação, cookies e publicidade.",
             "body": [
                 p(f"Esta política descreve como {o} {name} ({domain}) trata informações de "
                   f"quem visita o site."),
                 h2("Dados que coletamos"),
                 p("Não pedimos cadastro para ler o site e não coletamos nome, CPF ou "
                   "documento. Coletamos apenas dados de navegação agregados: páginas "
                   "visitadas, tempo de permanência, origem do acesso, tipo de dispositivo "
                   "e país aproximado."),
                 h2("Google Analytics"),
                 p("Usamos o Google Analytics 4 para entender o desempenho do site. Ele grava "
                   "cookies no seu navegador e trata o endereço IP de forma anonimizada. "
                   "Você pode bloquear esses cookies nas configurações do navegador ou pela "
                   "extensão oficial de opt-out do Google."),
                 h2("Publicidade"),
                 p("Este site exibe anúncios do Google AdSense. O Google e seus parceiros "
                   "podem usar cookies para exibir anúncios com base em visitas anteriores a "
                   "este e a outros sites. Você pode desativar a publicidade personalizada "
                   'nas <a href="https://www.google.com/settings/ads" rel="nofollow noopener" '
                   'target="_blank">configurações de anúncios do Google</a>.'),
                 h2("Newsletter"),
                 p("Se você assinar nossa newsletter, guardamos apenas o e-mail informado, "
                   "usado somente para enviar os próprios boletins. O cancelamento pode ser "
                   "feito a qualquer momento pelo link no rodapé de cada envio."),
                 h2("Seus direitos (LGPD)"),
                 p(f"Você pode solicitar acesso, correção ou exclusão dos seus dados pelo "
                   f"e-mail {mail}. Respondemos em até 15 dias."),
                 h2("Alterações"),
                 p("Mudanças nesta política são publicadas nesta mesma página, com a data de "
                   "atualização no topo."),
             ]},
            {"slug": "contato", "key": "contact", "title": "Contato",
             "description": f"Fale com a redação {do} {name}: pautas, correções e imprensa.",
             "body": [
                 p(f"O canal oficial de contato {do} {name} é o e-mail {mail}."),
                 h2("Para que serve cada assunto"),
                 ul(["<strong>Correção</strong>: envie o link da matéria e o ponto específico "
                     "a corrigir. Priorizamos esse tipo de mensagem.",
                     "<strong>Sugestão de pauta</strong>: conte o fato e indique onde ele foi "
                     "publicado ou anunciado.",
                     "<strong>Imprensa e releases</strong>: aceitamos, mas releases não viram "
                     "matéria sozinhos — dependem de confirmação independente.",
                     "<strong>Publicidade</strong>: nossa monetização hoje é feita por redes "
                     "de anúncio; não vendemos conteúdo patrocinado."]),
                 h2("Prazo de resposta"),
                 p("Lemos todas as mensagens. Correções são respondidas em até 2 dias úteis; "
                   "os demais assuntos, conforme a disponibilidade da redação."),
             ]},
            {"slug": "termos", "key": "terms", "title": "Termos de Uso",
             "description": f"Condições de uso do conteúdo publicado {no} {name}.",
             "body": [
                 p(f"Ao navegar em {domain} você concorda com os termos abaixo."),
                 h2("Uso do conteúdo"),
                 p("Os textos publicados aqui são originais e protegidos por direito autoral. "
                   "É permitido citar trechos curtos com crédito e link para a matéria "
                   "original. Não é permitida a reprodução integral sem autorização prévia."),
                 h2("Natureza da informação"),
                 p("Publicamos jornalismo sobre tecnologia. Nada no site constitui "
                   "aconselhamento de investimento, jurídico ou profissional. Decisões "
                   "tomadas com base no conteúdo são de responsabilidade do leitor."),
                 h2("Conteúdo assistido por IA"),
                 p("Nossas matérias são produzidas com apoio de inteligência artificial sob "
                   "um processo de checagem em múltiplas fontes. Ainda assim, erros podem "
                   "ocorrer — e por isso mantemos um canal de correção aberto."),
                 h2("Links externos"),
                 p("Matérias linkam para as fontes usadas na apuração. Não respondemos pelo "
                   "conteúdo, pelas políticas nem pela disponibilidade desses sites."),
                 h2("Disponibilidade"),
                 p("O site é oferecido no estado em que se encontra, sem garantia de "
                   "funcionamento ininterrupto."),
             ]},
        ]

    if lang == "en":
        return [
            {"slug": "about", "key": "about", "title": f"About {name}",
             "description": f"What {name} is, and how our stories are produced and checked.",
             "body": [
                 p(f"{name} is a news site covering {niche}: model releases, market moves, "
                   f"regulation and the practical use of AI inside companies, in Brazil and "
                   f"worldwide."),
                 h2("How our stories are produced"),
                 p("Our editorial production is AI-assisted and runs on a fixed verification "
                   "process. Every story follows the same path:"),
                 ul(["Collection of recent reporting from established news sources;",
                     "Cross-checking: a fact only enters the text if at least two mutually "
                     "independent sources confirm it;",
                     "Original writing from the confirmed facts — never a copy or a close "
                     "paraphrase of the source text;",
                     "Automated checks on originality, structure and source citation before "
                     "publication."]),
                 p("Stories that fail any of these steps are not published: they are held for "
                   "human review or dropped."),
                 h2("Transparency"),
                 p("Every story lists the sources used. When sources disagree on a number or "
                   "a detail, we say so in the text instead of hiding it."),
                 h2("Corrections"),
                 p(f"Found an error? Write to {mail} with the link. Meaningful corrections are "
                   f"flagged on the page itself."),
             ]},
            {"slug": "privacy", "key": "privacy", "title": "Privacy Policy",
             "description": f"How {name} handles browsing data, cookies and advertising.",
             "body": [
                 p(f"This policy explains how {name} ({domain}) handles information about "
                   f"people who visit the site."),
                 h2("What we collect"),
                 p("Reading the site requires no account, and we do not collect names or "
                   "identity documents. We collect aggregate browsing data only: pages "
                   "viewed, time on page, referral source, device type and approximate "
                   "country."),
                 h2("Google Analytics"),
                 p("We use Google Analytics 4 to understand how the site performs. It stores "
                   "cookies in your browser and processes IP addresses in anonymised form. "
                   "You can block these cookies in your browser settings or with Google's "
                   "official opt-out extension."),
                 h2("Advertising"),
                 p("This site shows Google AdSense ads. Google and its partners may use "
                   "cookies to serve ads based on your prior visits to this and other sites. "
                   'You can turn off personalised advertising in your <a '
                   'href="https://www.google.com/settings/ads" rel="nofollow noopener" '
                   'target="_blank">Google ad settings</a>.'),
                 h2("Newsletter"),
                 p("If you subscribe, we store only the e-mail address you provide, used "
                   "solely to send the newsletter. You can unsubscribe at any time via the "
                   "link at the bottom of every issue."),
                 h2("Your rights"),
                 p(f"You may request access to, correction of, or deletion of your data at "
                   f"{mail}. We reply within 15 days."),
                 h2("Changes"),
                 p("Any change to this policy is published on this page, with the update "
                   "date at the top."),
             ]},
            {"slug": "contact", "key": "contact", "title": "Contact",
             "description": f"Reach the {name} newsroom: tips, corrections and press.",
             "body": [
                 p(f"The official contact channel for {name} is {mail}."),
                 h2("What to send"),
                 ul(["<strong>Correction</strong>: send the story link and the specific point "
                     "to fix. These get priority.",
                     "<strong>Story tip</strong>: tell us the fact and where it was published "
                     "or announced.",
                     "<strong>Press and releases</strong>: welcome, but a release alone is "
                     "never a story — it needs independent confirmation.",
                     "<strong>Advertising</strong>: we monetise through ad networks and do "
                     "not sell sponsored content."]),
                 h2("Response time"),
                 p("We read everything. Corrections are answered within two business days; "
                   "other subjects as the newsroom's schedule allows."),
             ]},
            {"slug": "terms", "key": "terms", "title": "Terms of Use",
             "description": f"Conditions for using content published on {name}.",
             "body": [
                 p(f"By browsing {domain} you agree to the terms below."),
                 h2("Use of content"),
                 p("The texts published here are original and protected by copyright. Short "
                   "quotations are allowed with credit and a link to the original story. Full "
                   "reproduction requires prior permission."),
                 h2("Nature of the information"),
                 p("We publish technology journalism. Nothing on this site is investment, "
                   "legal or professional advice. Decisions taken on the basis of our content "
                   "are the reader's responsibility."),
                 h2("AI-assisted content"),
                 p("Our stories are produced with the support of artificial intelligence under "
                   "a multi-source verification process. Errors can still happen — which is "
                   "why the corrections channel stays open."),
                 h2("External links"),
                 p("Stories link to the sources used. We are not responsible for the content, "
                   "policies or availability of those sites."),
                 h2("Availability"),
                 p("The site is provided as is, with no guarantee of uninterrupted service."),
             ]},
        ]

    return [
        {"slug": "acerca", "key": "about", "title": f"Acerca de {name}",
         "description": f"Qué es {name} y cómo se producen y verifican nuestras notas.",
         "body": [
             p(f"{name} es un sitio de noticias dedicado a la {niche}. Cubrimos lanzamientos "
               f"de modelos, movimientos de mercado, regulación y aplicaciones prácticas de "
               f"IA en empresas, en Brasil y en el mundo."),
             h2("Cómo se producen las notas"),
             p("Nuestra producción editorial es asistida por inteligencia artificial y opera "
               "sobre un proceso fijo de verificación. El flujo es el mismo para toda nota:"),
             ul(["Recolección de notas recientes en fuentes periodísticas establecidas;",
                 "Verificación cruzada: un dato solo entra en el texto si aparece confirmado "
                 "en al menos dos fuentes independientes entre sí;",
                 "Redacción original a partir de los datos confirmados, sin copia ni paráfrasis "
                 "cercana del texto fuente;",
                 "Verificación automática de originalidad, estructura y cita de fuentes antes "
                 "de publicar."]),
             p("Las notas que no pasan por todas esas etapas no se publican: quedan retenidas "
               "para revisión humana o se descartan."),
             h2("Transparencia"),
             p("Cada nota lista al final las fuentes usadas. Cuando las fuentes difieren sobre "
               "un dato, lo decimos en el texto en lugar de esconderlo."),
             h2("Correcciones"),
             p(f"¿Encontraste un error? Escríbenos a {mail} con el enlace de la nota. Las "
               f"correcciones relevantes se señalan en la propia página."),
         ]},
        {"slug": "privacidad", "key": "privacy", "title": "Política de Privacidad",
         "description": f"Cómo {name} trata datos de navegación, cookies y publicidad.",
         "body": [
             p(f"Esta política describe cómo {name} ({domain}) trata la información de quienes "
               f"visitan el sitio."),
             h2("Datos que recopilamos"),
             p("No pedimos registro para leer el sitio y no recopilamos nombre ni documentos "
               "de identidad. Solo recopilamos datos de navegación agregados: páginas vistas, "
               "tiempo de permanencia, origen del acceso, tipo de dispositivo y país "
               "aproximado."),
             h2("Google Analytics"),
             p("Usamos Google Analytics 4 para entender el desempeño del sitio. Guarda cookies "
               "en tu navegador y trata la dirección IP de forma anonimizada. Puedes bloquear "
               "esas cookies en la configuración del navegador o con la extensión oficial de "
               "exclusión de Google."),
             h2("Publicidad"),
             p("Este sitio muestra anuncios de Google AdSense. Google y sus socios pueden usar "
               "cookies para mostrar anuncios según tus visitas previas a este y a otros "
               'sitios. Puedes desactivar la publicidad personalizada en la <a '
               'href="https://www.google.com/settings/ads" rel="nofollow noopener" '
               'target="_blank">configuración de anuncios de Google</a>.'),
             h2("Newsletter"),
             p("Si te suscribes, guardamos solo el correo informado, usado únicamente para "
               "enviar los boletines. Puedes cancelar cuando quieras con el enlace al pie de "
               "cada envío."),
             h2("Tus derechos"),
             p(f"Puedes solicitar acceso, corrección o eliminación de tus datos escribiendo a "
               f"{mail}. Respondemos en hasta 15 días."),
             h2("Cambios"),
             p("Los cambios en esta política se publican en esta misma página, con la fecha de "
               "actualización arriba."),
         ]},
        {"slug": "contacto", "key": "contact", "title": "Contacto",
         "description": f"Escribe a la redacción de {name}: temas, correcciones y prensa.",
         "body": [
             p(f"El canal oficial de contacto de {name} es {mail}."),
             h2("Para qué sirve cada asunto"),
             ul(["<strong>Corrección</strong>: envía el enlace de la nota y el punto específico "
                 "a corregir. Priorizamos ese tipo de mensaje.",
                 "<strong>Sugerencia de tema</strong>: cuéntanos el hecho e indica dónde fue "
                 "publicado o anunciado.",
                 "<strong>Prensa y comunicados</strong>: los recibimos, pero un comunicado solo "
                 "no se convierte en nota: depende de confirmación independiente.",
                 "<strong>Publicidad</strong>: hoy monetizamos con redes de anuncios; no "
                 "vendemos contenido patrocinado."]),
             h2("Plazo de respuesta"),
             p("Leemos todos los mensajes. Las correcciones se responden en hasta 2 días "
               "hábiles; los demás asuntos, según la disponibilidad de la redacción."),
         ]},
        {"slug": "terminos", "key": "terms", "title": "Términos de Uso",
         "description": f"Condiciones de uso del contenido publicado en {name}.",
         "body": [
             p(f"Al navegar en {domain} aceptas los términos siguientes."),
             h2("Uso del contenido"),
             p("Los textos publicados aquí son originales y están protegidos por derecho de "
               "autor. Se permite citar fragmentos cortos con crédito y enlace a la nota "
               "original. No se permite la reproducción integral sin autorización previa."),
             h2("Naturaleza de la información"),
             p("Publicamos periodismo sobre tecnología. Nada en el sitio constituye "
               "asesoramiento de inversión, jurídico o profesional. Las decisiones tomadas a "
               "partir del contenido son responsabilidad del lector."),
             h2("Contenido asistido por IA"),
             p("Nuestras notas se producen con apoyo de inteligencia artificial bajo un "
               "proceso de verificación en múltiples fuentes. Aun así pueden ocurrir errores: "
               "por eso mantenemos abierto el canal de correcciones."),
             h2("Enlaces externos"),
             p("Las notas enlazan a las fuentes usadas. No respondemos por el contenido, las "
               "políticas ni la disponibilidad de esos sitios."),
             h2("Disponibilidad"),
             p("El sitio se ofrece tal como está, sin garantía de funcionamiento "
               "ininterrumpido."),
         ]},
    ]


def main() -> None:
    cfg = load()
    now = isoformat(utcnow())
    total = 0
    for lang in cfg.languages:
        folder = OUT / lang
        folder.mkdir(parents=True, exist_ok=True)
        for page in pages_for(lang, cfg):
            path = folder / f"{page['slug']}.json"
            existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            payload = {**page, "lang": lang,
                       "updated_at": now if existing.get("body") != page["body"]
                       else existing.get("updated_at", now)}
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            total += 1
        print(f"  /{lang}/  {len(pages_for(lang, cfg))} páginas")
    print(f"{total} páginas institucionais em content/pages/")


if __name__ == "__main__":
    main()
