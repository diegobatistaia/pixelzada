# Como replicar o sistema da Pixelzada em outro projeto

Guia para levar a máquina de vídeos (e, se quiser, o site inteiro) da Pixelzada
para o **Cortexplor** e para as **marcas novas** (GTA 6, carros, tecnologia e
mercado financeiro), cada uma com site, domínio e Instagram próprios.
Escrito em 09/11/2026.

Você não precisa saber GitHub nem programar. A divisão é sempre esta:

- **Você** cria as contas e copia as chaves (as partes que pedem seu login).
- **O Claude** copia os arquivos, troca a marca, liga os robôs e testa.

Onde aparecer **[VOCÊ]** é passo seu, com clique a clique. Onde aparecer
**[CLAUDE]** é só pedir no projeto novo.

Arquivos que acompanham este guia:

| Arquivo | Para que serve |
|---|---|
| `docs/replicar/marca-modelo.yaml` | Ficha da marca nova: tudo o que muda, num lugar só |
| `scripts/tools/onde_trocar.py` | Mostra onde o nome antigo ainda aparece no código (hoje: ~600 linhas em ~80 arquivos) |

---

## 1. Arquitetura recomendada para 6 marcas

O plano (09/11/2026) é ter **6 marcas**: Pixelzada e Cortexplor, que já
existem, e quatro novas: **GTA 6** (marca própria, com outro posicionamento,
independente da Pixelzada), **notícias de carros**, **tecnologia** e
**mercado financeiro**.

Com esse número, copiar a Pixelzada à mão a cada vez vira bagunça: seis
cópias que vão ficando diferentes, e cada melhoria tem de ser repetida seis
vezes. Também não vale juntar tudo num sistema só, porque um token vencido ou
um erro derrubaria as seis de uma vez.

**Recomendação: um molde único + uma configuração por marca, com contas e
chaves sempre separadas.** Pense em "uma planta de casa, seis casas".

```
            ┌──────────────────────────────────────────┐
            │  REPOSITÓRIO MODELO  (diegobatistaia/    │
            │  marca-modelo)  =  o "molde"             │
            │  motor de pesquisa, download, montagem,  │
            │  fila, Gaveta, publicação, site, skills  │
            │  + marca.yaml em branco                  │
            └───────┬──────────┬──────────┬────────────┘
       "Use this    │          │          │   melhorias entram
        template"   ▼          ▼          ▼   primeiro no molde
                 marca A    marca B    marca C ...
                 (repo,     (repo,     (repo,
                 Instagram, Instagram, Instagram,
                 chaves,    chaves,    chaves,
                 projeto    projeto    projeto
                 Claude)    Claude)    Claude)
```

| | Tudo num sistema só | Cópia manual da Pixelzada | **Molde + config por marca (recomendado)** |
|---|---|---|---|
| Criar marca nova | rápido, depois de semanas de construção | ~1 dia de trocas no código | 1 clique ("Use this template") + preencher `marca.yaml` |
| Token vencido / conta bloqueada | pode derrubar todas | só aquela | só aquela |
| Erro num robô | atinge todas | só aquela | só aquela |
| Melhoria nova | vale para todas na hora | repetir 6 vezes, à mão | entra no molde; o Claude leva para cada marca com 1 pedido |
| Memória e regras do Claude | misturadas | separadas | separadas, cada marca com seu projeto |
| Risco para a Pixelzada | alto (mexe no que já roda) | nenhum | nenhum (a Pixelzada só serve de origem) |

**Como chegar lá, em duas fases:**

- **Fase 1, o molde (trabalho do Claude, sem cliques seus).** Criar o
  repositório `marca-modelo` a partir da Pixelzada, tirando dele tudo o que
  está "escrito à mão" com o nome, os horários, o CTA e os temas da Pixelzada
  (hoje são ~600 linhas em ~80 arquivos, ver Apêndice A) e fazendo o código ler
  tudo de um arquivo só, `marca.yaml` (a ficha `marca-modelo.yaml` deste
  guia). O molde fica marcado como **Template repository** no GitHub.
  A Pixelzada **não muda** nessa fase.
- **Fase 2, as marcas.** Cada marca nova nasce do molde (seção 5). Depois
  que 2 ou 3 estiverem rodando, dá para avaliar se a Pixelzada e o Cortexplor
  também passam a seguir o molde (só com o seu OK, e sem pressa).

Enquanto o molde não existe, este guia funciona do mesmo jeito copiando
direto da Pixelzada (é o que a seção 5.3 descreve); só dá mais trabalho ao
Claude.

**O que é compartilhado entre as marcas** (pode ser o mesmo):

- Sua conta do GitHub (com o app do Claude liberado para todos os repositórios).
- A conta da Hostinger (cada marca é um domínio novo nela; confira no hPanel
  se o seu plano aceita mais sites).
- Sua conta de desenvolvedor do Facebook (developers.facebook.com).
- O app da Meta que **publica** (o do Cortexplor já publica na Pixelzada).
- O molde (código, robôs, molduras, instruções do Claude).

**O que é de cada marca** (nunca reaproveitar):

- Repositório no GitHub, domínio, Instagram, Página do Facebook.
- Todas as chaves: Instagram, pesquisa, Telegram, SSH de deploy.
- App da Meta da **pesquisa** (um por marca: se a Meta restringir um app,
  só aquela marca para) e robô do Telegram.
- Identidade visual, concorrentes, temas, horários, CTA, tom, fontes de notícia.
- Projeto no Claude (memória e instruções próprias), rotinas e Gaveta de Reels.

---

## 1.1 Pontos de atenção por marca

**Mercado financeiro (o mais sensível).**
- Notícia e explicação, nunca recomendação. Nada de "compre", "venda",
  "vai subir", preço-alvo ou carteira sugerida. Recomendar ativo específico é
  atividade regulada pela CVM (analista/consultor certificado).
- Aviso fixo em todo lugar: bio do Instagram, legenda de cada post, rodapé
  de cada matéria e página "Sobre": *"Conteúdo informativo. Não é recomendação
  de investimento."* O molde precisa de um campo `aviso_legal` na ficha que o
  robô coloca sozinho.
- Cotação e número sempre com **data, hora e fonte** (ex.: B3, Banco Central).
  Post com cotação velha é o erro mais comum.
- Concorrentes "influenciadores de investimento" vendem curso e sinal: entram
  na lista de palavras bloqueadas (`curso`, `mentoria`, `sinal`, `lucro garantido`,
  `renda passiva`, `day trade`).
- O Google trata finanças como assunto delicado: o AdSense e a busca cobram
  mais autoria e fonte. Página "Sobre" com quem escreve e política de correção.

**GTA 6 (marca nova, diferente da Pixelzada).**
- Marca independente, com posicionamento e público próprios. Para não
  disputar com a Pixelzada: lista de concorrentes, temas e estilo de moldura
  diferentes, e o robô **não** posta o mesmo vídeo nas duas contas (o Claude
  liga um histórico de "já usados" que as duas marcas consultam, sem misturar
  o resto).
- O lançamento é 19/11/2026: depois dele o assunto muda de "trailer e
  espera" para "guias, missões e segredos". Planejar o segundo momento já na
  ficha.

**Notícias de carros.**
- Vídeo de montadora e de canais de teste costuma ter música licenciada e
  marca d'água: o robô já descarta "sem arquivo"; marca d'água é cortada
  ou o vídeo é pulado.
- Preço e ficha técnica variam por país: sempre o dado do Brasil, com fonte.

**Tecnologia.**
- Muito rumor de lançamento (celular, IA, console): marcar **rumor** no
  título quando não há anúncio oficial; fonte oficial basta sozinha quando é
  anúncio da própria empresa (regra que o site já tem).

**Para todas.**
- **Direitos autorais**: os Reels usam vídeos de outros perfis sem crédito
  (decisão sua na Pixelzada). Com 6 contas o risco de denúncia/strike cresce;
  convém dar crédito nas marcas novas, ao menos na legenda.
- **GitHub**: repositórios públicos têm minutos grátis ilimitados, mas a
  conta grátis roda no máximo 20 tarefas ao mesmo tempo. Com 6 marcas rodando
  de 10 em 10 minutos, o Claude escalona os horários (uma marca no :00, outra
  no :02...) para não formar fila.
- **Uso do Claude**: cada marca tem suas rotinas (redação, lista das 6h20,
  conferências, vigia). Seis marcas são seis vezes mais rodadas; comece cada
  marca nova com menos rodadas e suba aos poucos.
- **Hostinger**: um único IP para todas. Quando ele mudar (como em 01/11), as
  6 marcas param juntas: o vigia de erros de cada marca confere o IP primeiro.

---

## 2. Mapa do sistema (o que existe na Pixelzada)

```
  Concorrentes no Instagram          Você (link no Telegram)
            │                                  │
   [Pesquisa 6h] lê os vídeos          [Telegram, 10 em 10 min]
   e faz a lista do dia                        │
            │  Claude manda a lista,           │
            │  você responde números           │
            ▼                                  ▼
       [Baixar] yt-dlp grátis ──► social/reels/entrada/
                                       │
                         [Montar Reels] moldura da marca (20 estilos)
                                       │
                         social/reels/fila.json  ──► Gaveta de Reels (página)
                                       │
                         [Reels, 10 em 10 min] envia o vídeo para
                         <domínio>/ig/ e publica no Instagram
```

| Peça | Arquivos principais | Robô (Actions) |
|---|---|---|
| Motor de pesquisa | `scripts/social/pesquisa.py`, `social/pesquisa/config.yaml` | `pesquisa.yml` |
| Download de links | `scripts/social/pesquisa.py` (yt-dlp) | `pesquisa.yml` (botão `link`) |
| Robô do Telegram | `scripts/social/telegram.py` | `telegram.yml` |
| Montagem na identidade | `scripts/social/montagem.py`, `scripts/social/gerador/` | `montar.yml` |
| Fila e publicação de Reels | `scripts/social/reels.py`, `social/reels/fila.json` | `reels.yml` |
| Gaveta de Reels | `scripts/social/gaveta.py` | (o Claude publica a página) |
| Carrosséis e Stories | `scripts/social/instagram.py`, `arte.py`, `pauta.py`, `templates/social/` | `instagram.yml` |
| Site de matérias | `scripts/engine/`, `scripts/pipeline/`, `templates/`, `site.config.yaml` | `coletar.yml`, `finalizar.yml`, `deploy.yml`, `capas.yml`, `promover.yml`, `analytics.yml` |
| Instruções do Claude | `.claude/skills/` (redação, Instagram, voz da marca) | (rotinas do Claude) |

Detalhe importante: o Instagram só aceita vídeo/imagem por **link público**.
Por isso o robô envia cada mídia para `https://<domínio>/ig/...` antes de
publicar. **Toda marca precisa de um domínio com SSH**, mesmo que não tenha
site de matérias.

---

## 3. O que copiar e o que trocar

Cole a ficha `marca-modelo.yaml` preenchida e o Claude troca tudo. Para você
saber o que está mudando:

| O que | Na Pixelzada | Na marca nova |
|---|---|---|
| Nome, slogan, descrição | Pixelzada, "Notícias de Games" | o seu |
| Domínio e e-mail | pixelzada.com.br, contato@pixelzada.com.br | o seu |
| Hospedagem (SSH) | Hostinger 82.112.247.46:65002, usuário u433721675 | mesma conta serve; pasta do domínio novo |
| Instagram | @pixelzada.br | o seu |
| Chave de publicar | secret `INSTAGRAM_TOKEN_PIXELZADA` | `INSTAGRAM_TOKEN_<MARCA>` |
| Chave da pesquisa | secret `META_TOKEN_PIXELZADA` (app "Pixelzada Pesquisa") | `META_TOKEN_<MARCA>` (app "<Marca> Pesquisa") |
| Chave do Telegram | secret `TELEGRAM_TOKEN_PIXELZADA` | `TELEGRAM_TOKEN_<MARCA>` |
| Chave de deploy | secret `HOSTINGER_SSH_KEY` (chave só da Pixelzada) | chave nova, mesmo nome de secret |
| Identidade | noite #0B0A10, lima #C6FF1A, magenta #FF3D8B; Anton, Archivo, Silkscreen; logos em `assets/logo/` e `scripts/social/gerador/` | sua paleta, fontes e logos |
| Concorrentes e temas | 17 perfis de games; temas GTA 6, Battlefield 6, Forza Horizon 6 | os do seu nicho |
| Horários de Reels | 6/dia (10h a 20h), depois 15/dia e 25/dia (aquecimento GTA 6) | começar com 6/dia |
| Horários de carrossel | 9h a 21h nas horas ímpares; Story só no de GTA 6 | os seus |
| CTA do Reel | "Essa é a página pra seguir e acompanhar o GTA 6 / o universo dos games" | mesma regra, com o seu assunto |
| Hashtag da marca | `#pixelzada` | a sua |
| Tom e regras da redação | `.claude/skills/voz-pixelzada`, `redacao-diaria`, `instagram-pixelzada` | renomear e adaptar |
| Fontes de notícia (RSS) | sites de games em `site.config.yaml` | as do seu nicho |
| Robô no Git | `pixelzada-bot` / bot@pixelzada.com.br | `<marca>-bot` |

**O que NÃO se copia** (o repositório novo começa vazio nisso): matérias
publicadas (`pt/`, `content/`, `data/`), vídeos e fila (`social/reels/`),
coletas e listas da pesquisa, pautas e resultados do Instagram.

---

## 4. Antes de começar: o que ter em mãos

- [ ] Nome da marca e @ do Instagram (crie o Instagram antes; deixe como profissional, passo 5.4).
- [ ] Domínio comprado (Hostinger é o mais simples, porque já é sua conta).
- [ ] Logo e cores (ou peça ao Claude para criar a identidade, como foi na Pixelzada).
- [ ] 10 a 20 perfis concorrentes do Instagram que você acompanha.
- [ ] O app do Telegram no celular.
- [ ] Uns 60 a 90 minutos para os seus cliques, que podem ser divididos em dias.

---

## 5. Passo a passo de montagem (nesta ordem)

### 5.1 [VOCÊ] Criar o projeto no Claude

1. Abra o Claude e crie um **projeto novo** com o nome da marca.
2. Nas instruções do projeto, cole o texto do **Apêndice B** (troque os nomes).
3. Em [Configurações do projeto], adicione o repositório quando ele existir (passo 5.2).
4. Mande no chat do projeto a mensagem pronta do **Apêndice C**.

### 5.2 [VOCÊ] Criar o repositório no GitHub (2 minutos)

**Quando o molde já existir (Fase 1 pronta):**

1. Abra https://github.com/diegobatistaia/marca-modelo
2. Clique no botão verde **Use this template** (canto de cima, à direita) > **Create a new repository**.
3. Siga do item 2 abaixo (nome, Public, Create repository).

**Enquanto o molde não existir:**

1. Abra https://github.com/new
2. Em **Repository name**, escreva o nome da marca em minúsculas, sem espaço (ex.: `novamarca`).
3. Marque **Public** (público). Motivo: repositório público tem minutos grátis
   ilimitados no GitHub Actions. A Pixelzada parou de 20/10 a 31/10 quando era
   privada e estourou o limite. Não há chave no código: elas ficam nos Secrets.
4. Não marque mais nada. Clique no botão verde **Create repository**.
5. Avise o Claude: "criei o repositório novamarca".

O app do Claude já está liberado para todos os seus repositórios, então ele
enxerga o novo na hora.

### 5.3 [CLAUDE] Copiar o sistema e trocar a marca

O Claude faz:

1. Copia o código da Pixelzada (sem matérias, vídeos, fila e históricos).
2. Aplica a ficha `marca-modelo.yaml`: nome, domínio, @, nomes dos secrets,
   cores, fontes, logos, concorrentes, temas, horários, CTA, hashtag.
3. Renomeia as skills (`voz-pixelzada` → `voz-<marca>` etc.) e adapta o tom.
4. Roda `python scripts/tools/onde_trocar.py pixelzada` até não sobrar nada.
5. Deixa os robôs **desligados** até as chaves existirem (eles avisam e saem sem erro).
6. Abre um PR e junta.

### 5.4 [VOCÊ] Instagram profissional (celular, 2 minutos)

1. Abra o Instagram na conta nova.
2. Toque na sua foto (canto de baixo, à direita).
3. Toque nas **três linhas** (canto de cima, à direita) > **Tipo de conta e ferramentas**.
4. **Mudar para conta profissional** > **Continuar** nas telas.
5. Categoria: a mais próxima do nicho (ex.: **Site de notícias**) > **Concluir**.
6. Escolha **Criador de conteúdo** ou **Empresa** > **Avançar**. Pode pular o resto.

### 5.5 [VOCÊ] Domínio e chave de deploy na Hostinger (10 minutos)

1. Entre no **hPanel** da Hostinger (hpanel.hostinger.com).
2. Se o domínio não estiver como site: **Sites** > **Adicionar site** > escolha o domínio novo.
3. Abra o site do domínio novo > **Segurança** > **SSL** e confirme que está **Ativo**.
4. Vá em **Avançado** > **Acesso SSH**. Confirme que o SSH está **Ativo** e
   anote o **IP**, a **porta** e o **usuário** que aparecem ali (mande para o Claude;
   não são segredo). Atenção: esse IP pode mudar com o tempo; foi o que derrubou
   o deploy da Pixelzada de 01/11 a 03/11.
5. O Claude gera um par de chaves só da marca nova e te manda **a chave pública**
   (uma linha que começa com `ssh-ed25519`). Na mesma tela **Acesso SSH**, clique em
   **Adicionar chave SSH**, dê o nome `deploy-<marca>`, cole a linha e salve.
6. A **chave privada** vai no GitHub como secret `HOSTINGER_SSH_KEY` (como cadastrar: passo 5.9).
   O Claude te entrega a chave privada num arquivo para você copiar e colar; depois apague o arquivo.

### 5.6 [VOCÊ] Chave de publicar no Instagram (15 minutos)

Serve para o robô publicar carrosséis, Stories e Reels.

1. Abra https://developers.facebook.com/apps e entre com a sua conta do Facebook.
2. Clique no app que você já usa para publicar (o do Cortexplor serve).
3. Menu da esquerda: **Instagram** > **Configuração da API com login do Instagram** (API setup with Instagram login).
4. Na seção **2. Gerar tokens de acesso**, clique em **Adicionar conta** (Add account).
5. Entre com o **Instagram novo** e clique em **Permitir** (Allow).
6. Ao lado da conta, clique em **Gerar token** (Generate token), marque o aviso e clique em **Copiar** (Copy).
7. Cadastre no GitHub como `INSTAGRAM_TOKEN_<MARCA>` (passo 5.9).

Se der erro de permissão: **Funções do app** > **Funções** > **Adicionar pessoas** >
**Testador do Instagram**, digite o @ novo; depois, logado no Instagram novo, abra
https://www.instagram.com/accounts/manage_access/ > **Convites de testador** > **Aceitar** e volte ao passo 4.

### 5.7 [VOCÊ] Chave do motor de pesquisa (20 minutos, uma vez só)

É outra chave, diferente da de publicar: a de publicar **não** lê concorrentes.
Esta é uma chave de Página do Facebook, que **nunca expira**.

**Parte A: ligar o Instagram a uma Página do Facebook (celular)**

1. No Instagram novo: sua foto > **Editar perfil** > **Página**.
2. Toque em **Criar Página do Facebook**, dê o nome da marca e conclua
   (ou **Conectar**, se a Página já existir).

**Parte B: criar o app da pesquisa (computador)**

1. https://developers.facebook.com/apps > **Criar app** (Create app).
2. Nome: **<Marca> Pesquisa**. **Avançar**.
3. Caso de uso: **Outro** (Other) > **Avançar**. Tipo: **Empresa** (Business) > **Avançar**.
4. Portfólio: **Sem portfólio** ou o da marca > **Criar app**.

**Parte C: gerar a chave**

1. Abra https://developers.facebook.com/tools/explorer
2. Em **App da Meta**, escolha **<Marca> Pesquisa**. Em **Usuário ou Página**, escolha **Obter token de acesso do usuário**.
3. Em **Permissões**, adicione estas seis: `instagram_basic`, `instagram_manage_insights`,
   `ads_read`, `pages_show_list`, `pages_read_engagement`, `business_management`.
   (Sem `instagram_manage_insights` a pesquisa dá erro #10.)
4. **Gerar token de acesso** > **Continuar**, marque a Página e o Instagram da marca, confirme.
5. Clique no **i** azul ao lado da chave > **Abrir na Ferramenta de token de acesso**.
6. No fim da página: **Estender token de acesso** (Extend Access Token) > **Copiar** a chave nova.
7. Volte ao Explorer, cole essa chave no campo **Token de acesso**.
8. Na barra do meio, troque `me?fields=id,name` por `me/accounts?fields=name,access_token` e clique em **Enviar**.
9. No bloco com o nome da sua Página, copie o texto entre aspas depois de `"access_token":`.
10. Confira em https://developers.facebook.com/tools/debug/accesstoken > **Depurar**: "Expira" tem de dizer **Nunca**.
11. Cadastre no GitHub como `META_TOKEN_<MARCA>` (passo 5.9).

### 5.8 [VOCÊ] Robô do Telegram (5 minutos)

1. No Telegram, busque **BotFather** (selo azul) > **Iniciar**.
2. Envie `/newbot`. Nome: o da marca. Usuário: algo como `<marca>_fila_bot` (tem de terminar em `bot`).
3. Copie a linha parecida com `1234567890:AAH...` que ele responde.
4. Cadastre no GitHub como `TELEGRAM_TOKEN_<MARCA>` (passo 5.9).
5. Abra o link do seu bot (`t.me/<usuario_do_bot>`) e toque em **Iniciar**.
   A sua conversa vira a única que ele atende.

Depois, para mandar referência: no Instagram, **Compartilhar** > **Telegram** > seu bot.
Link de vídeo vira Reel; link de perfil vira concorrente.

### 5.9 [VOCÊ] Como cadastrar cada chave no GitHub (vale para todas)

1. Abra `https://github.com/diegobatistaia/<repositorio>/settings/secrets/actions/new`
   (troque `<repositorio>` pelo nome do passo 5.2).
2. Em **Name**, escreva o nome exato (ex.: `META_TOKEN_NOVAMARCA`).
3. Em **Secret**, cole a chave (Ctrl+V).
4. Clique em **Add secret**.

**Nunca cole uma chave na conversa com o Claude.** Só no GitHub. Os nomes
(não as chaves) você pode mandar à vontade.

| Secret | O que é | Passo |
|---|---|---|
| `HOSTINGER_SSH_KEY` | chave privada de deploy (só desta marca) | 5.5 |
| `INSTAGRAM_TOKEN_<MARCA>` | publicar no Instagram | 5.6 |
| `META_TOKEN_<MARCA>` | ler concorrentes (pesquisa) | 5.7 |
| `TELEGRAM_TOKEN_<MARCA>` | robô do Telegram | 5.8 |
| `UNSPLASH_ACCESS_KEY`, `PEXELS_API_KEY` | imagens de reserva do site (opcional) | – |
| `GA_SEARCH_CONSOLE_CREDENTIALS` | métricas semanais (opcional, depois) | – |

### 5.10 [CLAUDE] Ligar e testar, um robô por vez

Avise "cadastrei as chaves" e o Claude roda, nesta ordem:

1. **Deploy**: publica o site (ou só a pasta `/ig/`) e confere o domínio.
2. **Instagram > teste**: confere se a chave é do @ certo.
3. **Pesquisa > teste**: lê um concorrente. Os perfis que a API não enxerga saem da lista.
4. **Telegram**: você manda um link de Reel para o bot e ele responde.
5. **Montar Reels**: monta 2 ou 3 vídeos e você aprova o visual.
6. **Reels**: publica o primeiro no horário.

### 5.11 [CLAUDE] Rotinas e Gaveta

O Claude cria, no projeto novo (em claude.ai/code/routines):

- **Redação** (se tiver site): matérias + pautas dos carrosséis, de 2 em 2h.
- **Lista diária às 6h20**: manda os vídeos achados; você responde com os números.
- **Conferência dos posts** 5 min depois de cada horário, e disparo dos carrosséis no :58.
- **Vigia de erros do GitHub** de hora em hora.
- **Gaveta de Reels**: página nova, só desta marca, atualizada sempre que um Reel entra na fila.

E salva na memória do projeto as regras da marca (CTA, horários, concorrentes, tom).

---

## 6. Caso Cortexplor: levar só a parte dos vídeos

O Cortexplor já tem site e publicação de carrosséis (a Pixelzada nasceu de
uma cópia dele). Falta só a máquina de Reels. Nada no Cortexplor muda até
você pedir explicitamente no Claude.

**O que levar** (do repositório da Pixelzada para o do Cortexplor):

- `scripts/social/pesquisa.py`, `telegram.py`, `montagem.py`, `reels.py`, `gaveta.py`, `scripts/social/gerador/`
- `.github/workflows/pesquisa.yml`, `telegram.yml`, `montar.yml`, `reels.yml`
- `social/pesquisa/config.yaml` (com concorrentes e temas do Cortexplor)
- `social/reels/fila.json` vazio (`[]`)

**O que conferir antes** (o Claude faz):

1. Se o `scripts/social/instagram.py` do Cortexplor é compatível com o `reels.py`
   (os dois foram feitos juntos, mas o Cortexplor pode ter mudado).
2. **O IP da Hostinger no Cortexplor**: ele ainda usa o IP antigo
   (147.79.91.241) e o deploy dele falha. Os Reels dependem do envio para
   `cortexplor.../ig/`, então isso precisa ser corrigido junto (com o seu OK).
3. **Minutos do GitHub**: o robô de Reels roda de 10 em 10 minutos. Num
   repositório **privado** isso gasta ~2.500 minutos por mês só nele, mais
   que o limite grátis (2.000). Opções: deixar o Cortexplor **público** (como a
   Pixelzada) ou trocar para disparo só nos horários (6 por dia).
4. Os nomes dos secrets: `META_TOKEN_CORTEXPLOR` e `TELEGRAM_TOKEN_CORTEXPLOR`
   (novos, passos 5.7 e 5.8); a chave de publicar do Cortexplor já existe.
5. As molduras dos Reels com o logo, as cores e as fontes do Cortexplor.

**Seus cliques no caso Cortexplor:** só 5.7 (app "Cortexplor Pesquisa") e 5.8
(robô do Telegram), e decidir o item 3.

---

## 7. Checklist final

Contas e chaves
- [ ] Instagram profissional criado (5.4)
- [ ] Repositório público criado (5.2) e adicionado ao projeto do Claude
- [ ] Domínio com SSL e SSH ativos; IP/porta/usuário enviados ao Claude (5.5)
- [ ] Chave pública de deploy colada na Hostinger (5.5)
- [ ] `HOSTINGER_SSH_KEY` cadastrado (5.5)
- [ ] `INSTAGRAM_TOKEN_<MARCA>` cadastrado (5.6)
- [ ] Página do Facebook ligada ao Instagram e app "<Marca> Pesquisa" criado (5.7)
- [ ] `META_TOKEN_<MARCA>` cadastrado e "Expira: Nunca" conferido (5.7)
- [ ] Robô do Telegram criado, `TELEGRAM_TOKEN_<MARCA>` cadastrado, /start enviado (5.8)

Montagem (Claude)
- [ ] Ficha `marca-modelo.yaml` preenchida
- [ ] `onde_trocar.py pixelzada` sem resultados
- [ ] Identidade aplicada no site, nos carrosséis e nas 20 molduras de Reel
- [ ] Concorrentes, temas, horários e CTA da marca no `social/pesquisa/config.yaml` e no `reels.py`
- [ ] Skills renomeadas e com o tom da marca

Testes
- [ ] Deploy verde e domínio abrindo
- [ ] Teste do Instagram ok
- [ ] Teste da pesquisa ok (perfis que falham removidos)
- [ ] Link pelo Telegram virou Reel
- [ ] Primeiro Reel publicado no horário
- [ ] Rotinas criadas e Gaveta de Reels publicada
- [ ] Regras da marca salvas na memória do projeto

---

## 8. Ordem resumida (para colar num papel)

1. Instagram profissional → 2. Repositório público → 3. Projeto no Claude com a
ficha → 4. Claude copia e troca a marca → 5. Hostinger (SSH + chave) →
6. Chave de publicar → 7. Chave da pesquisa → 8. Telegram → 9. Claude testa
→ 10. Rotinas e Gaveta.

---

## 9. Como levar melhorias de uma marca para as outras

Como as marcas são separadas, uma melhoria numa delas (ex.: novo estilo de
moldura) não aparece sozinha nas outras. O caminho é sempre passar pelo molde:

1. Na marca onde a melhoria nasceu, peça: *"leve esta melhoria para o
   repositório marca-modelo, sem nada específico desta marca"*.
2. Em cada outra marca, peça: *"traga do marca-modelo a melhoria
   '<o que mudou>' para este projeto, adaptando a marca"*.

Assim uma marca nunca mexe direto no repositório da outra.
Enquanto o molde não existe, a origem é a própria Pixelzada:

> Traga do repositório diegobatistaia/pixelzada a melhoria "<o que mudou>"
> para este projeto, adaptando a marca. Não mexa em nada da Pixelzada.

Mantenha este guia atualizado (ele mora na Pixelzada e, depois, no molde).
Sempre que algo grande mudar, peça "atualize o GUIA-REPLICAR".

---

## Apêndice A. Onde a marca está no código (para o Claude)

Além do que o `onde_trocar.py` acha, estes pontos têm **regras da marca**
(não só o nome) e precisam de decisão:

| Arquivo | O que tem |
|---|---|
| `site.config.yaml` | site, marca, cores, fontes, logos, social, bot, SEO, fontes RSS, deploy (host/porta/usuário/pasta) |
| `social/pesquisa/config.yaml` | marca, conta, `segredo`, concorrentes, temas e pesos, palavras bloqueadas, coletas, modo lançamento |
| `scripts/social/instagram.py` | `USUARIO`, `SECRET`, `CARROSSEIS` (horários e temas), `STORY_SO_GTA` |
| `scripts/social/reels.py` | `HORARIOS`, `GRADE_15`, `GRADE_25` e as datas em `horarios()` (aquecimento GTA 6: tirar na marca nova) |
| `scripts/social/montagem.py` | `SEGUE` (CTA por tema), `TAGS`, `CORES`, `PROMPT` do título, hashtag `#pixelzada` |
| `scripts/social/pauta.py` | `MARCA` (hashtag obrigatória) |
| `scripts/social/telegram.py` | `SEGREDO`, texto `AJUDA` |
| `scripts/social/gerador/` | `estilos.js` (logo, @, 20 molduras), SVGs dos logos, `fonts/` |
| `scripts/social/gaveta.py` | texto da página da Gaveta |
| `templates/social/` | `marca.css`, `fontes/`, estilos dos carrosséis (rodapé com @ e domínio) |
| `templates/site.css.j2`, `assets/logo/` | paleta e logos do site |
| `.github/workflows/*.yml` | nomes dos secrets em `env:`, nome do passo "Enviar para <domínio>/ig/", `git config user.name/email` |
| `.claude/skills/*` | voz da marca, redação diária, regras do Instagram |
| `SETUP.md`, `README.md`, `social/INSTAGRAM.md` | textos com a marca |

## Apêndice B. Texto para as instruções do projeto novo no Claude

```
Projeto da marca <MARCA> (@<instagram>, <domínio>). Repositório:
diegobatistaia/<repositorio>. Sistema copiado da Pixelzada
(diegobatistaia/pixelzada, guia docs/replicar/GUIA-REPLICAR.md),
ou do molde diegobatistaia/marca-modelo quando ele existir.
NÃO alterar o repositório da Pixelzada nem o do Cortexplor sem pedido explícito.
Conversar sempre em português. O Diego usa Windows e não sabe GitHub:
quando algo depender dele, passo a passo clique a clique.
REGRA FIRME: sempre que um Reel entrar na fila, atualizar a Gaveta de Reels
desta marca na hora. CTA do Reel só chama para seguir: "Essa é a página pra
seguir e acompanhar <assunto>". Agir sem pedir aprovação em coisas óbvias do plano.
```

## Apêndice C. Primeira mensagem para o projeto novo

```
Quero replicar o sistema da Pixelzada nesta marca nova. Siga o guia
docs/replicar/GUIA-REPLICAR.md do repositório diegobatistaia/pixelzada.
Criei o repositório diegobatistaia/<repositorio> (público).
Ficha da marca: <cole aqui a marca-modelo.yaml preenchida, ou diga
"me ajude a preencher">.
Copie o sistema, troque a marca, deixe os robôs desligados até as chaves
existirem e me diga quais passos [VOCÊ] do guia faltam.
```
