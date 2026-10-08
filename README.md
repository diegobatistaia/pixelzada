# Pixelzada

Site de notícias de games em português (`/pt/`), com o GTA 6 como carro-chefe,
gerado como HTML estático e publicado automaticamente por rsync.

A base veio do Cortexplor (`diegobatistaia/cortexplor`), copiada em 08/10/2026
sem histórico e sem matérias. Os dois repositórios são independentes: nada aqui
altera o Cortexplor, e correções no motor de um precisam ser copiadas à mão para
o outro.

Não há CMS, banco de dados nem painel. O site é um repositório: o pipeline escreve
arquivos, o GitHub Actions sincroniza com o servidor.

## Como funciona

```
RSS/APIs  ->  checagem cruzada  ->  redação por idioma  ->  gate  ->  HTML  ->  rsync
             (2+ fontes indep.)     (Skill de voz)         (7 critérios)
```

O site roda em **modo Routine**: a checagem e a redação são feitas por uma sessão
do Claude Code agendada na nuvem, sob a assinatura, sem custo de API. Os scripts
fazem o trabalho determinístico dos dois lados.

| Etapa | Quem faz | Custo |
|---|---|---|
| coleta dos feeds | `run brief` | zero |
| checagem e redação | a Routine, seguindo `redacao-diaria` | assinatura |
| imagem, gate, build | GitHub Actions (`Finalizar`) | zero |
| deploy | GitHub Actions (`Deploy`) | zero |

O modo API — `run all`, que faz tudo sozinho chamando a API — continua no
repositório para quando houver orçamento. Ver o fim deste arquivo.

Uma pauta só vira matéria se **dois donos de fonte diferentes** confirmarem os fatos
centrais. Veículos do mesmo grupo contam como uma fonte só — republicação não é
confirmação. O que não passa no gate vai para `data/queue/` e espera revisão humana;
nada é publicado com ressalva.

## Estrutura

```
site.config.yaml          toda a configuração específica DESTE site
scripts/
  engine/                 o motor, genérico — nada de nicho hardcoded
    config.py             carrega e valida o site.config.yaml
    collect.py            1. coleta RSS + filtro de palavras-chave + clusterização
    verify.py             2. checagem cruzada de fatos (regra das 2 fontes)
    draft.py              3-4. ângulo por idioma + redação com a Skill de voz
    seo.py                5. URLs, hreflang, JSON-LD, links internos
    images.py             6. imagem licenciada (Unsplash/Pexels) + atribuição
    gate.py               7. o gate de qualidade
    build.py              8. gera todo o site estático
    llm.py                único ponto de chamada da API do Claude
    i18n.py               textos de interface (pt/en/es)
  pipeline/run.py         orquestrador: all | collect | build | queue | status
  tools/                  utilitários de uma vez só (páginas, demo, autoteste)
scripts/social/           Instagram: pautas, gerador de artes e publicação
social/                   pautas do Instagram e o guia (social/INSTAGRAM.md)
templates/                HTML e CSS (Jinja2); templates/social/ é a moldura do Instagram
content/pt/*.json         as matérias (fonte da verdade)
content/pages/pt/          páginas institucionais
data/                     índice de publicados, fila de exceção, log do gate
assets/                   logo, fontes, CSS e imagens
pt/                       HTML gerado — é isto que vai para o ar
```

## Comandos

```bash
python -m scripts.pipeline.run status     # modo, fase do ramp, taxa do gate, fila
python -m scripts.pipeline.run brief      # coleta e baixa o texto das fontes
python -m scripts.pipeline.run check      # valida os rascunhos antes do commit
python -m scripts.pipeline.run finish     # imagem + gate + build (roda no Actions)
python -m scripts.pipeline.run queue      # o que está esperando revisão
python -m scripts.pipeline.run build      # só regerar o HTML
```

O ciclo diário é `brief` → a Routine lê o briefing, checa e escreve → `check` →
commit e push → o Actions faz `finish` e publica.

Para ver o site localmente:

```bash
python -m http.server 4173
```

E abrir <http://localhost:4173/pt/>.

## Ferramentas de uma vez só

```bash
python scripts/tools/selfcheck.py         # 91 verificações, sem gastar API
python scripts/tools/make_pages.py        # regera as páginas institucionais
python scripts/tools/demo_content.py      # enche o site de posts falsos (layout)
python scripts/tools/demo_content.py --clean
```

## O que é provisório

- **Identidade visual.** Já aplicada a partir de `identidade/` (pasta do
  projeto): logo e símbolo em `assets/logo/`, paleta `noite`/`lima` em
  `templates/site.css.j2`, Anton, Archivo e Silkscreen pelo Google Fonts
  (`brand.fonts` no config) e o recorte em degrau nas imagens.
- **Imagem das matérias.** Hoje vem do Unsplash. A identidade pede o trailer ou
  o print oficial dentro da arte; isso ainda precisa entrar em
  `scripts/engine/images.py`.
- **Fontes RSS.** A lista em `sources.rss` foi montada sem poder testar os
  feeds. A primeira execução do workflow **Coletar** mostra quais responderam.
- **Links de afiliado.** Ainda não há suporte no template.

## Voltar para o modo API

Quando fizer sentido pagar por uso (mais volume, ou vontade de tirar a Routine
do caminho):

1. Crie o secret `ANTHROPIC_API_KEY` no GitHub.
2. Descomente o bloco `schedule` em `.github/workflows/publish.yml`.
3. Desligue a Routine em <https://claude.ai/code/routines>.

O `run all` já está escrito e testado; `verify.py` e `draft.py` continuam no
repositório justamente para isso. Nada mais muda: gate, build e deploy são os
mesmos nos dois modos.

## O que falta configurar

Ver [SETUP.md](SETUP.md).
