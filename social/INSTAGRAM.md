# Instagram da Pixelzada (@pixelzada.br)

Tudo sai sozinho, em horários fixos (Brasília):

| Horário | O que sai |
|---|---|
| 08h e 18h | carrossel de GTA 6 + Story |
| 12h e 21h | carrossel de outro jogo + Story |
| 19h30 | Reel do carrossel de GTA 6 mais recente do dia |

São 4 carrosséis por dia, metade GTA 6 e metade outros jogos. Horário de GTA 6
sem pauta de GTA 6 pega outro jogo; horário de outro jogo só usa GTA 6 se sobrar.

## Como funciona

```
Routine da redação  ->  social/pautas/<slug>.json  ->  workflow Instagram (Actions)
(texto, imagem, legenda)                               desenha -> envia para
                                                       pixelzada.com.br/ig/<slug>/ ->
                                                       publica pela API -> grava o resultado
```

1. **Redação.** A Routine diária, depois das matérias, escreve as pautas
   seguindo `.claude/skills/instagram-pixelzada/SKILL.md` e confere com
   `python -m scripts.social.instagram check`.
2. **Desenho.** `scripts/social/arte.py` monta cada slide com a moldura da
   identidade visual (`templates/social/`, cópia do `marca.css` e das fontes) e
   fotografa no Chromium. Texto que não cabe reprova a pauta (status
   `reprovado`, com o motivo) e o horário pega a próxima.
3. **Mídia pública.** O Instagram busca as imagens por URL. O workflow envia a
   pasta do post para `public_html/ig/<slug>/` na Hostinger, com a mesma chave
   do deploy. O deploy do site não apaga essa pasta (`/ig/` no
   `deploy.exclude`).
4. **Publicação.** `scripts/social/instagram.py` usa a API do Instagram com
   login do Instagram (`graph.instagram.com`), a mesma do Cortexplor. Antes de
   publicar, confere que a chave é do @pixelzada.br. O Story sai logo depois do
   carrossel; se ele falhar, o carrossel não é repetido.
5. **Registro.** A pauta ganha `publicado` (data, horário, link), `story` e
   `reel`. O último resultado fica em `social/publicar/ultimo.json`.

O Reel é feito dos próprios slides: a capa do Reel e cada slide na moldura
vertical, com uma trilha 8-bit gerada pelo código (sem música de terceiros).

## Comandos

```bash
python -m scripts.social.instagram agenda        # o que saiu hoje e o que há na fila
python -m scripts.social.instagram fila          # pautas prontas, vencidas e reprovadas
python -m scripts.social.instagram check         # confere as pautas prontas
python -m scripts.social.arte <slug> [--reel]    # desenha em social/saida/<slug>/
```

No GitHub: **Actions > Instagram > Run workflow**, com `teste` (a chave
funciona e é da conta certa?), `conferir` (últimos posts da conta) ou `rodada`
(publica se for horário).

## Chave do Instagram

Secret `INSTAGRAM_TOKEN_PIXELZADA` no repositório. A chave vale 60 dias e cada
publicação estica a validade de novo; se a conta ficar 60 dias sem publicar,
é preciso gerar outra e trocar o secret.

## Limites conhecidos

- A API não põe figurinha de link no Story. O Story diz "Matéria completa no
  link da bio".
- A imagem vem do `og:image` das fontes no briefing. A Routine não vê a
  imagem; a regra de escolha está na skill.
- Formatos com duas imagens (expectativa x realidade, comparativo) ainda não
  estão no gerador.
