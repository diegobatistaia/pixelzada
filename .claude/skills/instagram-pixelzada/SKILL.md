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

A redação roda de 2 em 2 horas. Em cada rodada, rode antes:

```bash
python -m scripts.social.instagram agenda
```

Ele mostra o que já saiu hoje e quantas pautas há na fila. Escreva **uma pauta
para cada matéria nova da rodada**, e só isso. Não escreva mais do que 4 por
rodada.

## De onde vem o assunto: sempre de uma matéria (Diego, 12/10)

Diego viu os carrosséis de GTA 6 repetindo as mesmas coisas (as seis rádios, os
podcasts, o "não tem streaming exclusivo no Xbox") porque saíam 3 por dia em
cima de 4 matérias. A regra agora é:

1. **Toda pauta nasce de uma matéria do site** (`"materia": "<slug>"`, o arquivo
   `content/pt/<slug>.json`), de preferência a que você acabou de escrever.
2. **Uma matéria vira um carrossel só.** Não existe segundo carrossel da mesma
   matéria, nem com outro formato ou outro título. O `check` reprova.
3. **Os slides contam só o que está naquela matéria.** Nada de recapitular fato
   de outra matéria ("seis rádios", "sem streaming exclusivo", "data mantida")
   para encher slide. Se a matéria é curta, o carrossel tem 2 slides.
4. **Acabaram as pautas de enchimento.** Checagem, guia ou "faltam N dias" sem
   matéria por trás não saem mais. O guia, a checagem e a contagem continuam
   existindo como **matéria no site** (que vira carrossel depois).
5. **Faltou matéria de GTA 6?** O horário de GTA 6 fica com outro jogo; o
   workflow já faz isso sozinho. Um carrossel repetido é pior que um GTA 6 a
   menos. Para não faltar, a redação escreve mais matérias de GTA 6 no site
   (ver `redacao-diaria`).
6. **Antes de escrever, olhe as últimas pautas** de `social/pautas/` do mesmo
   grupo (GTA 6 ou outros jogos): o gancho da capa e o primeiro slide não podem
   repetir o de nenhuma delas.

## O formato (varia sempre)

Além do estilo visual (automático), cada pauta tem um `formato`: o jeito de
contar a matéria. **O formato não pode ser o mesmo das duas últimas pautas do
mesmo grupo** (o `check` confere). Escolha o que a matéria pede:

| `formato` | Quando usar | Como fica |
| --- | --- | --- |
| `manchete` | notícia direta | capa com o fato; slides: o que aconteceu, o que muda pra quem joga, o que falta saber |
| `perguntas` | assunto que gera dúvida | cada slide é uma pergunta do leitor no título ("Vai ter no PC?") e a resposta no texto |
| `linha-do-tempo` | história com datas | slide com `passos`, cada passo começa pela data ("Dez 2023: primeiro trailer") |
| `em-numeros` | matéria com números | cada slide abre com um número no título ("15 horas por mês no Ultimate") |
| `lista` | várias novidades de uma vez | "5 coisas que...": um item por slide, com o porquê |
| `detalhes` | trailer, imagens, anúncio | "o que passou batido": um detalhe por slide, só o que a matéria descreve |
| `comparativo` | antes e agora, um contra o outro | capa com `lados`; slides lado a lado |
| `em-foco` | personagem, lugar, jogo, pessoa | capa com `ficha` ou `local`; perfil em 2 a 4 slides |
| `passo-a-passo` | guia prático | slide com `passos` |
| `mito-ou-verdade` | boato que circula | o único com selos (`itens`); no máximo 1 a cada 4 pautas |
| `debate` | assunto que divide | os fatos dos dois lados e o `final` é uma pergunta para comentar |

O `check` confere o mínimo de cada um: pergunta com "?", número em algarismo,
data em cada passo, `lados` no comparativo, `ficha` ou `local` no em-foco, pelo
menos 3 slides em lista e detalhes, e selos só no mito-ou-verdade.

## O arquivo

Um por post, em `social/pautas/<slug>.json`. Exemplo completo em
`social/exemplo-pauta.json` (formato mito-ou-verdade).

```json
{
  "slug": "gta-6-xbox-cloud-gaming-pc-checagem",
  "tipo": "noticia | checagem | guia",
  "formato": "manchete | perguntas | linha-do-tempo | em-numeros | lista | detalhes | comparativo | em-foco | passo-a-passo | mito-ou-verdade | debate",
  "assunto": "GTA 6",
  "gta6": true,
  "materia": "slug-da-materia-no-site (obrigatório)",
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
visível na capa, como no CSS `object-position`; quando a foto tem rosto, o
desenho ignora o `pos` e enquadra no rosto (ver abaixo).

**Nunca cortar nem cobrir o rosto de personagem (regra do Diego, 12/10).** Em
todo slide, Story e capa de Reel o personagem aparece com a cabeça inteira e a
cena bem enquadrada: nada de testa, olhos ou queixo cortados pela moldura, e
nenhum texto, selo, logo ou faixa por cima do rosto. O desenho acha os rostos
da foto (`scripts/engine/rosto.py`) e põe todos os slides nesse ponto; o que
fica com você:
- Use imagem deitada (16:9) em boa resolução, com o personagem à vista;
  nunca a versão em pé de celular (URL com `mobile`, `portrait`, `9x16`). Há
  muito material oficial de GTA 6 (screenshots da Rockstar, trailers, Xbox
  Wire): procure uma boa em vez de aceitar uma ruim.
- Nunca arte com faixa ou fundo desfocado nas laterais da foto: a imagem
  preenche a moldura inteira.
- Não escolha imagem em que o rosto está colado na borda ou já cortado na
  origem (close em que só aparece boca ou olhos).
- Ao revisar as artes, se algum slide cortar ou cobrir um rosto, troque a
  imagem antes de publicar.


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
- **Vazamento de GTA 6 rende carrossel** (Diego, 12/10), desde que exista a
  matéria do vazamento no site. A capa diz "vazamento" ou "segundo o insider X"
  e os slides contam o que vazou sem repetir "não confirmado" em cada um. A
  imagem é sempre oficial, nunca o print vazado. Para vazamento, prefira os
  formatos `detalhes`, `lista`, `debate` ("acha que é real?") e `perguntas`.
- **Selos não são regra** (Diego, 09/10): carrossel de notícia e de guia não leva
  lista de selos nem a palavra "confirmado/rumor" em todo slide. Use `itens`
  com selo só no formato **mito-ou-verdade**, e no máximo 1 a cada 4 pautas.
  O resto é conteúdo para chamar atenção: gancho forte na capa (reação, meme,
  número, pergunta), um fato por slide, frase curta. Informar sem virar boletim.
  Quando o assunto for vazamento, a palavra "vazamento" na capa já diz tudo;
  não precisa avisar de novo em cada slide.

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

- Escrever pauta sem matéria, ou um segundo carrossel da mesma matéria.
- Encher slide com fato de outra matéria já postada.
- Mudar `status`, `publicado`, `story` ou `reel` de uma pauta que já saiu.
- Apagar pauta publicada: ela é o histórico que impede repetir post.
- Mexer em `templates/social/` ou na moldura para o texto caber: encurte o texto.
- Usar imagem de outro criador de conteúdo, print de vídeo de youtuber ou foto
  de pessoa tirada de matéria.
