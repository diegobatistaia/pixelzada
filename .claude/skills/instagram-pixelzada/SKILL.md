---
name: instagram-pixelzada
description: Como escrever as pautas do Instagram da Pixelzada (@pixelzada.br) - carrossel e Story que saem sozinhos em horários fixos. Use ao fechar a rodada da redação diária ou sempre que for criar, revisar ou corrigir um arquivo em social/pautas/.
---

# Pautas do Instagram (@pixelzada.br)

Você escreve o texto; o resto é automático. Cada pauta vira um carrossel com
Story junto, publicado pelo workflow **Instagram** do GitHub Actions num dos
horários fixos. Você não desenha nada, não publica nada e não precisa de
internet.

Leia antes `.claude/skills/voz-pixelzada/SKILL.md`: a voz é a mesma do site.

## Quantas e quando

São **7 carrosséis por dia, 3 de GTA 6 e 4 de outros jogos** (decisão do Diego
em 08/10 e 09/10). Horários (Brasília, grade de 12/10): **11h, 15h e 19h para GTA 6**; **09h, 13h,
17h e 21h para outros jogos**. Os Reels de vídeo saem nas horas pares, entre eles. O Reel está desligado desde 09/10. A fila é FIFO: a pauta mais antiga
sai primeiro. Notícia vence em 36 horas, checagem em 4 dias e guia em 7 dias;
pauta vencida não sai.

A redação roda três vezes por dia. Em cada rodada, rode antes:

```bash
python -m scripts.social.instagram agenda
```

Ele mostra o que já saiu hoje e quantas pautas há na fila. A meta é a fila
nunca secar: **cerca de 1 de GTA 6 e 1 de outros jogos por rodada**, menos se a
fila já estiver cheia. Não escreva mais do que 4 por rodada.

## De onde vem o assunto

1. **Cada matéria que você acabou de escrever para o site** pode virar uma pauta
   (`"materia": "<slug da matéria>"`). É o caminho principal.
2. **GTA 6 sem notícia nova no dia.** São 3 por dia, e nem todo dia tem
   notícia de GTA 6. Complete com:
   - **checagem** ("o que se sabe"): boatos que estão no briefing contra o que
     já foi confirmado, com selos;
   - **guia**: passos práticos com fatos já publicados (pré-venda, edições,
     plataformas, preparar o console);
   - **contagem e resumo**: "faltam N dias" com o que já está confirmado.

   Todo fato da pauta tem que estar no briefing (passando pela regra das duas
   fontes) ou numa matéria já publicada em `content/pt/`. Nada de memória, nada
   de "todo mundo sabe".

Não repita a mesma pauta em dias seguidos: confira `social/pautas/` antes.

## O arquivo

Um por post, em `social/pautas/<slug>.json`. Exemplo completo em
`social/exemplo-pauta.json` (formato checagem).

```json
{
  "slug": "gta-6-xbox-cloud-gaming-pc-checagem",
  "tipo": "noticia | checagem | guia",
  "assunto": "GTA 6",
  "gta6": true,
  "materia": "slug-da-materia-no-site ou vazio",
  "criado": "2026-10-08T07:40:00-03:00",
  "imagem": {"url": "https://...", "credito": "Rockstar Games", "pos": "50% 40%"},
  "fonte": "Fontes: The Verge e Eurogamer",
  "capa": {"titulo": "...", "destaque": "trecho do título", "apoio": "..."},
  "slides": [
    {"rotulo": "O que muda", "titulo": "...", "destaque": "...", "texto": ["§1", "§2"]},
    {"rotulo": "O que se sabe", "titulo": "...", "itens": [{"selo": "confirmado", "texto": "..."}]},
    {"rotulo": "Passo a passo", "titulo": "...", "passos": ["...", "..."]}
  ],
  "final": "Manda pro amigo que...",
  "legenda": {"gancho": "...", "corpo": ["...", "..."], "chamada": "...", "hashtags": ["#pixelzada", "#gta6", "..."]},
  "alt": ["Slide 1: ...", "Slide 2: ...", "..."],
  "status": "pronto"
}
```

- `criado`: agora, com o fuso `-03:00`. É dele que sai a ordem da fila e o vencimento.
- `gta6`: `true` só se o post é sobre GTA 6. É o que decide o horário.
- `assunto`: o nome curto do jogo ou tema, até 16 caracteres ("GTA 6", "Xbox", "Gears E-Day").
- `slides`: de 2 a 5, cada um com **um só** entre `texto` (1 ou 2 parágrafos),
  `itens` (até 5, com selo) ou `passos` (até 5, numerados em sequência).
  `**negrito**` funciona dentro de `texto`. O carrossel fica com capa + slides + final.
- Selos: `confirmado`, `boato`, `falso`, `sem-info`.
- `destaque` (na capa e nos slides): uma ou duas palavras **copiadas do título**,
  que saem na cor de destaque.
- `final`: a frase do último slide, pedindo envio ("Manda pro amigo que...").
  O aviso "Matéria completa no link da bio" já vem pronto no slide.
- `fonte`: começa com "Fonte:" ou "Fontes:", até 46 caracteres. Vai na faixa de baixo.
- `status`: sempre `"pronto"`. O workflow muda para `publicado` (ou `reprovado`,
  com o motivo, se o texto não couber na arte).

## A imagem

Toda arte tem o print ou o quadro do trailer dentro da moldura, com crédito.
Você não vê a imagem, então escolha pela origem:

1. **`image` das fontes no briefing** (o `og:image` da página). Prefira a da
   fonte `primary` (Rockstar Newswire, PlayStation Blog, Xbox Wire): é material
   oficial de divulgação.
2. `image` de uma fonte de imprensa **só quando a matéria é sobre material
   oficial do jogo** (trailer, screenshots, capa). Se a matéria é sobre uma
   pessoa, uma empresa ou um processo, a imagem provavelmente é foto de
   agência: não use.

**Nunca repita imagem.** Cada carrossel tem a sua. Antes de escolher, rode
`python -m scripts.social.instagram imagens`: ele lista a imagem de cada pauta
já publicada ou na fila (hoje e dias recentes). A imagem da nova pauta não pode
ser a mesma de nenhuma delas, nem com outro recorte ou tamanho (o `?w=1200` não
conta como outra imagem). `check` reprova a repetição e o workflow não publica
pauta com imagem repetida.

Se a única imagem disponível já foi usada, procure outra: a `image` de outra
fonte do briefing (prefira a oficial, Rockstar Newswire, PlayStation Blog, Xbox
Wire) ou a imagem de outra matéria do site sobre o mesmo assunto. Sem imagem
diferente e adequada, não escreva a pauta: um GTA 6 a menos é melhor que um
carrossel repetido.

`credito` é o dono da imagem, não o site onde ela estava: "Rockstar Games",
"Sony", "Xbox Game Studios". `pos` (opcional) diz qual parte da imagem fica
visível na capa, como no CSS `object-position`.


## Estilo do carrossel (automático)

O workflow escolhe sozinho um dos **21 estilos** de `templates/social/estilos/`
(decisão do Diego em 09/10): nunca o mesmo estilo em dias seguidos, e o que está
há mais tempo sem sair vai primeiro, para todos aparecerem. Você não escolhe o
estilo; só escreve a pauta. Prévia dos 20: `identidade/estilos-novos/` na pasta
do projeto.

Quatro estilos só entram se a capa tiver um campo extra, e outros ficam melhores
com o seu. **Sempre que a notícia permitir de verdade, preencha um destes na
`capa`** (sem inventar: o valor sai do fato da pauta):

| Campo na `capa` | Libera ou melhora | Exemplo |
| --- | --- | --- |
| `numero` (até 6) e `numero_legenda` (até 30) | Numerão | `"26"`, `"de janeiro de 2027"` |
| `citacao` (até 90) e `autor` (até 50) | Aspas | frase dita por alguém, com aspas só no texto da fonte |
| `lados` (2 nomes até 14) | Versus | `["GTA 5", "GTA 6"]` |
| `data` (AAAA-MM-DD) | Agenda | `"2026-11-19"` (data confirmada de lançamento ou evento) |
| `ficha` (2 a 4 pares) | Ficha | `[["Lança", "19 nov 2026"], ["Onde", "PS5 e Xbox Series"]]` |
| `itens_capa` (2 a 4 nomes até 16) | Inventário | jogos de uma lista |
| `local` (até 20) | Mapa | `"Vice City"` |
| `palavra` (até 12) | Pôster | o nome do jogo em uma palavra: `"Muramasa"` |
| `chefe` (até 20) | Chefão | o "vilão" da notícia: `"Os Salvadores"` |
| `fala` (até 40) | Quadrinho | uma fala curta de personagem, tirada do material oficial |

`citacao` é sempre uma frase que a fonte atribui à pessoa, traduzida sem mudar
o sentido. `fala` de personagem só se estiver no trailer ou no texto oficial.

## Texto

- **Capa:** título de até 80 caracteres, com reação ou meme no gancho
  ("Segura o coração", "Calma lá"); `apoio` com o fato e um "arrasta".
- **Slides:** fato checado, frase curta, atribuição ("segundo a Rockstar").
  Título do slide até 60 caracteres; `texto` até 460 caracteres somando os parágrafos.
- **Sem emoji na arte** e no máximo um ponto de exclamação no carrossel inteiro.
- Boato só aparece como boato (no texto, ou com selo `boato`/`sem-info`), nunca como fato.
- **Selos não são regra** (Diego, 09/10): carrossel de notícia e de guia não leva
  lista de selos nem a palavra "confirmado/rumor" em todo slide. Use `itens`
  com selo só em pauta de **checagem**, e no máximo 1 checagem a cada 4 pautas.
  O resto é conteúdo para chamar atenção: gancho forte na capa (reação, meme,
  número, pergunta), um fato por slide, frase curta. Informar sem virar boletim.
  Quando o assunto for rumor, o tom diz isso ("ainda é boato", "sem confirmação
  da Rockstar") dentro da frase, sem tabela de selos.

## Legenda

Montada assim: `gancho` + `corpo` + `chamada` + "Matéria completa no link da
bio." + hashtags.

- `gancho`: até 125 caracteres (é o que aparece antes do "mais"), com o nome do
  jogo e o fato.
- `corpo`: 2 ou 3 parágrafos curtos com o contexto que não coube nos slides.
  Atribuição sempre. **Nenhum link nem domínio.**
- `chamada`: uma pergunta para comentar ("Você tinha caído nessa?") ou um
  pedido de envio. Alterne entre os dois.
- Legenda sem as hashtags entre 350 e 1.100 caracteres.
- `hashtags`: de 3 a 5, a primeira é `#pixelzada`, minúsculas e sem acento
  (`#gta6`, `#rockstargames`, `#ps5`). Nada genérico como `#games` ou `#gamer`.
- `alt`: um por slide, na ordem, começando por "Slide N: ", até 120 caracteres.

## Conferir e commitar

```bash
python -m scripts.social.instagram check
```

Corrija até zerar. Se o ambiente tiver Chromium, desenhe e olhe a folha:

```bash
python -m scripts.social.arte <slug>     # social/saida/<slug>/folha.png
```

Depois, no mesmo commit das matérias (ou sozinho):

```bash
git add social/pautas
git commit -m "instagram: <n> pautas de <data>"
git push
```

## O que nunca fazer

- Mudar `status`, `publicado`, `story` ou `reel` de uma pauta que já saiu.
- Apagar pauta publicada: ela é o histórico que impede repetir post.
- Mexer em `templates/social/` ou na moldura para o texto caber: encurte o texto.
- Usar imagem de outro criador de conteúdo, print de vídeo de youtuber ou foto
  de pessoa tirada de matéria.
