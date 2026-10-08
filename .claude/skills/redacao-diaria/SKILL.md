---
name: redacao-diaria
description: Procedimento diário da redação da Pixelzada - checar as pautas de games do briefing contra a regra das duas fontes independentes e escrever as matérias em português. Use quando rodar o pipeline diário do site, seja numa Routine agendada na nuvem ou numa sessão manual.
---

# Fechamento diário da Pixelzada

Você é a redação. Seu trabalho hoje: pegar as pautas coletadas, decidir **quais
resistem à checagem**, e escrever as que resistirem. Nada além disso.

O que decide se o site é bom não é o volume publicado — é o que você **descarta**.
Um dia sem matéria é um resultado aceitável. Uma matéria com fato não confirmado
não é.

## 1. Ler o briefing do dia

```bash
python -m scripts.pipeline.run briefing
```

**Não rode `brief`.** Esta sessão não tem saída para a web — só PyPI e as APIs da
Anthropic passam pelo proxy, e qualquer feed de notícia volta com 403. A coleta
já aconteceu no GitHub Actions meia hora antes, e o resultado veio junto no
clone, em `data/briefing.json`.

O comando acima mostra o resumo e **falha se o briefing não for de hoje** (no
fuso do site) — sinal de que a coleta de hoje não rodou. Briefing de uma rodada
anterior **do mesmo dia** serve: se a coleta desta rodada falhou, escreva em cima
dele. O comando já tira as pautas que viraram matéria e recalcula o teto desta
rodada. (A coleta e esta sessão rodam três vezes por dia.) Se ele falhar, pare aqui:
escreva no resumo que o briefing está velho ou vazio e encerre sem commitar.
Escrever em cima de notícia de ontem é pior do que não publicar.

Depois de passar, leia `data/briefing.json` inteiro. Cada pauta traz `sources[]`,
e cada fonte tem `owner` (o grupo dono do veículo) e `text` (a matéria inteira,
quando foi possível baixar).

## 1.1 Hierarquia das fontes

Cada fonte no briefing traz um campo `kind`:

- **`primary`** — quem fez a notícia. O trailer no Newswire da Rockstar, o
  anúncio no PlayStation Blog ou no Xbox Wire, o comunicado da publisher.
- **`press`** — quem noticiou. IGN, GameSpot, Eurogamer, Voxel, Jovem Nerd.

**Quando existe primária, ela é a fonte da matéria.** A imprensa vira
corroboração e contexto, não origem. Citar a IGN pelo que a Rockstar
anunciou é citar o intermediário — e é o erro que este site não comete.

Na prática:

- A primária **entra sempre** em `sources`. O `check` reprova se ela existia no
  briefing e ficou de fora.
- No texto, atribua ao autor do fato: "segundo o Newswire da Rockstar",
  "de acordo com o PlayStation Blog". A imprensa entra quando acrescenta
  algo que a primária não tem — reação de mercado, contexto, contraponto.
- Com duas fontes independentes, a matéria segue a regra das duas fontes
  (seção 2), e a primária conta como uma delas.
- **Anúncio oficial sozinho** (regra herdada do Cortexplor; vale enquanto
  o briefing trouxer `official_announcement_alone: true`): quando a pauta é o
  anúncio que a **própria empresa** publicou no canal oficial dela e ainda não
  há segundo dono, ela pode virar matéria com essa fonte só. Condições, todas
  obrigatórias:
  - o fato é o que a empresa anunciou **sobre ela mesma** (produto, modelo,
    preço, data, trailer, plataforma, requisitos). Afirmação sobre outra empresa, sobre
    pessoas ou sobre o mercado continua exigindo duas fontes;
  - a fonte tem `kind: primary` e texto (`text`) no briefing; título sozinho
    não basta;
  - o texto atribui à empresa tudo o que ela afirma: "segundo a Rockstar",
    "a Sony afirma". Desempenho, números e promessas vão sempre como fala da
    empresa, nunca como fato;
  - a matéria leva o campo `"fonte_unica": "anuncio_oficial"` (o `check` e o
    gate conferem que a fonte é um canal oficial, e o site mostra um aviso
    próprio no rodapé).
  Se a imprensa também cobriu, use as duas fontes e não marque `fonte_unica`.
- Cuidado com o dono: IGN, Eurogamer, Rock Paper Shotgun e GamesIndustry.biz
  são todos IGN Entertainment (Ziff Davis); PlayStation Blog e PlayStation Blog
  BR são a Sony. Vários feeds, uma fonte.

**Cuidado com o release.** Fonte primária é autoritativa sobre o que a empresa
disse, não sobre se aquilo é verdade. "A empresa afirma que o modelo é 40% mais
rápido" é fato; "o modelo é 40% mais rápido" é publicidade repetida. Número de
desempenho que vem só do fabricante vai sempre atribuído.

## 2. Checar — a parte que só você faz

Para cada pauta do briefing, leia o texto de todas as fontes e separe os **fatos
centrais**: aqueles sem os quais a matéria não existe. Normalmente são de três a
seis (o que aconteceu, quem, quando, quanto, o que muda).

Um fato só está confirmado se **dois `owner` diferentes afirmam ele no texto**.

As regras que fazem essa conta ser honesta:

- **Owner, não veículo.** PC Gamer e GamesRadar são as duas da Future: contam
  como uma fonte. A lista de `owners` da pauta já vem no briefing.
- **Frase quase igual em duas fontes = mesmo release.** Isso é uma fonte só
  reproduzida duas vezes, não confirmação independente. Descarte a pauta ou
  registre a ressalva.
- **Número, data e nome próprio têm que bater.** Se as fontes divergem, ou você
  não usa o dado, ou diz no texto que as fontes divergem. Nunca escolha um valor
  e apresente como certo.
- **Não complete lacuna.** Se um dado seria útil e não está em nenhuma fonte, a
  matéria sai sem ele.
- **Fonte sem `text`** (não foi possível baixar) só vale pelo título. Título não
  confirma fato.

Descarte a pauta quando: menos de dois owners confirmam os fatos centrais (salvo
o anúncio oficial sozinho, nas condições da seção 1.1); as
fontes só repetem um comunicado; o assunto é lançamento comercial disfarçado de
notícia; ou você não entendeu o fato bem o suficiente para explicá-lo.

**O que interessa ao leitor deste site.** Ele joga e acompanha o que vem aí:
quer saber o que saiu, quando chega, quanto custa, em que plataforma roda e se
o rumor da semana é verdade. **GTA 6 vem primeiro**: até o lançamento
(19/11/2026), pauta confirmada de GTA 6 tem preferência sobre qualquer outra de
peso parecido. Depois, entre duas pautas igualmente bem apuradas, prefira a que
muda alguma coisa para quem joga (data, preço, trailer, atualização, promoção
oficial, requisito) em vez de bastidor de empresa. Rumor de GTA 6 sem
confirmação não vira matéria, por mais que circule.

Publique no máximo `posts_per_language_today` pautas (está no briefing). Esse
número é o teto **desta rodada**, não do dia: o briefing também traz
`daily_cap_per_language` e `already_written_today`, e o código já dividiu o que
sobra do dia entre as rodadas que faltam. Se sobrarem boas, deixe para a
próxima rodada — elas continuam no feed.

## 3. Escrever

Para **cada pauta aprovada**, escreva **uma matéria em português** (`pt`, o
único idioma em `languages`). Não é tradução da fonte: é a apuração reescrita do
zero, com o ângulo de quem joga no Brasil (preço em reais e lançamento no Brasil
só quando estiverem nos fatos confirmados).

A voz do site está em `.claude/skills/voz-pixelzada/SKILL.md`. **Leia antes de
escrever a primeira matéria.** Em resumo: solto no gancho, checado no corpo;
rumor só como rumor; data, preço e plataforma sempre com fonte; nenhuma aspa que
não esteja nos fatos confirmados.

Cite as fontes no corpo ("segundo a Rockstar", "de acordo com a IGN") — pelo menos uma, e isso é conferido automaticamente.

Escreva com a ortografia e a acentuação corretas do idioma. Um site de notícias
em português sem acento não passa.

## 4. Salvar

Um arquivo por matéria, em `content/<idioma>/<slug>.json`:

```json
{
  "lang": "pt",
  "slug": "gta-6-terceiro-trailer-vice-city",
  "story_id": "<copie o story_id da pauta no briefing>",
  "title": "Título de 55 a 70 caracteres, sem clickbait",
  "dek": "Uma frase de apoio, abaixo do título.",
  "meta_description": "Entre 150 e 160 caracteres, com a palavra-chave principal. Conte os caracteres.",
  "keyword": "palavra-chave principal",
  "category": "gta-6",
  "tags": ["gta 6", "rockstar", "trailer"],
  "body": [
    {"type": "p",  "text": "Primeiro parágrafo, com o fato principal.", "items": []},
    {"type": "p",  "text": "Segundo parágrafo.", "items": []},
    {"type": "h2", "text": "Subtítulo", "items": []},
    {"type": "p",  "text": "Mais texto.", "items": []},
    {"type": "list", "text": "", "items": ["Item um", "Item dois"]}
  ],
  "image": {
    "query": "busca em inglês (reserva, se a imagem da fonte falhar)",
    "alt": "Descrição da imagem no idioma do texto, com pelo menos 15 caracteres",
    "url": "URL do campo image de uma fonte da pauta no briefing",
    "credit": "Imagem: Xbox Wire"
  },
  "sources": [
    {"name": "Rockstar Newswire", "owner": "take-two", "url": "https://...", "title": "Título original"},
    {"name": "IGN", "owner": "ziff-davis", "url": "https://...", "title": "Título original"}
  ],
  "status": "draft"
}
```

Regras do arquivo:

- **Imagem do jogo.** Cada pauta do briefing traz `image` (o og:image da
  fonte). Copie a URL da fonte mais oficial da matéria (publisher, Xbox Wire,
  PlayStation Blog, Rockstar) para `image.url` e escreva `image.credit` como
  "Imagem: <nome da fonte>". O `alt` descreve o que a imagem mostra, sem
  inventar: se não souber, descreva o jogo e o assunto. Sem URL utilizável, a
  matéria sai com a capa própria da Pixelzada. Nunca use imagem de outro lugar.
- `slug` em minúsculas, sem acento, 3 a 8 palavras.
- `story_id` copiado da pauta: é o que evita escrever a mesma pauta duas vezes.
- `category` tem que estar em `categories_by_language.pt` no briefing:
  `gta-6`, `lancamentos`, `guias`, `consoles` ou `industria`.
- Todo bloco tem exatamente três campos: `type`, `text`, `items`. Use `items`
  só em `list`, e `text` vazio nesse caso.
- `sources` só com os owners que **confirmaram** os fatos, e sempre incluindo a
  primária quando o briefing tiver uma.
- `fonte_unica` só existe na matéria de anúncio oficial sozinho (seção 1.1), com o
  valor `"anuncio_oficial"`. Nas demais, não ponha o campo.
- `status` sempre `"draft"`. Quem promove para publicado é o gate.
- Corpo entre `word_count.min` e `word_count.max` palavras (está no briefing).

## 5. Conferir antes de commitar

```bash
python -m scripts.pipeline.run check
```

Ele aponta campo faltando, meta description fora da faixa, texto curto ou longo
demais, fonte não citada, categoria inexistente. **Corrija e rode de novo até
zerar.** Isso é de graça; o gate lá na frente não é.

## 5.1 Instagram

Depois das matérias, escreva as pautas do @pixelzada.br seguindo
`.claude/skills/instagram-pixelzada/SKILL.md` (carrosséis das matérias de hoje e
os de GTA 6 que faltarem na fila) e rode `python -m scripts.social.instagram check`
até zerar. Isso vale também numa rodada sem matéria nova: a fila do Instagram
precisa de GTA 6 todo dia.

## 6. Publicar

```bash
git add -A
git commit -m "content: <n> matérias de <data>"
git push
```

O push aciona o workflow **Finalizar** do GitHub Actions, que busca a imagem
licenciada, roda o gate de qualidade e publica no site. O que reprovar no gate vai para `data/queue/` em vez
de ir ao ar — e isso é o sistema funcionando, não um erro seu.

## 7. Antes de encerrar, verifique o AdSense

```bash
python -m scripts.pipeline.run status
```

Se a saída trouxer a linha **"ADSENSE: O SITE JÁ TEM LASTRO PARA PEDIR A ANÁLISE"**,
mande uma notificação push avisando — o dono do site pediu para ser avisado nesse
momento exato, e ele não fica olhando o painel todo dia.

A mensagem deve dizer quantas matérias existem, há quantos dias o site
está no ar, e que o próximo passo é pedir a análise em adsense.google.com. Mande
uma vez só: se a linha aparecer de novo nos dias seguintes, ele já foi avisado.

Se a linha não aparecer, não mande nada. Um push por dia dizendo "ainda não" é
ruído.

## O que nunca fazer

- Publicar fato com uma fonte só, por melhor que seja a fonte.
- Copiar ou parafrasear de perto uma frase da matéria-fonte.
- Inventar aspas, números, datas ou contexto.
- Traduzir a matéria-fonte em vez de reescrever a apuração.
- Editar arquivos em `pt/` (são gerados) ou mexer no gate
  para fazer uma matéria passar.
- Publicar acima do teto da rodada.

## Se não houver pauta

Se o briefing vier vazio, vier velho, ou nada resistir à checagem: escreva isso
no resumo e não escreva matéria. É um resultado legítimo e vai acontecer. As
pautas de GTA 6 do Instagram (seção 5.1) ainda podem sair com fatos de matérias
já publicadas; se não houver nem isso, encerre sem commitar.

## Onde cada etapa roda

| Etapa | Onde | Por quê |
|---|---|---|
| coleta dos feeds | GitHub Actions | é o único lugar com internet |
| checagem e redação | esta sessão | é o trabalho de julgamento |
| imagem, gate, build | GitHub Actions | precisa da chave do Unsplash e do gate determinístico |

Você é a etapa do meio. Não tente fazer as outras duas.
