# O que falta para o site entrar no ar

Ordem sugerida. Os itens 1 a 5 são o caminho crítico: com eles o site publica
sozinho. O resto pode vir depois.

A mecânica é a mesma do Cortexplor; o que muda é domínio, chaves e conteúdo.

---

## 1. Domínio e hospedagem

1. Registrar `pixelzada.com.br` (o site principal) e `pixelzada.com` (redirecionar
   para o `.com.br`).
2. Adicionar `pixelzada.com.br` na hospedagem e ativar o HTTPS.
3. Preencher o alvo de deploy no `site.config.yaml` e ligar o deploy:

   ```yaml
   deploy:
     enabled: true
     host: "..."
     port: 65002
     user: "..."
     remote_path: /home/<usuario>/domains/pixelzada.com.br/public_html/
   ```

Enquanto `deploy.enabled` for `false`, o workflow **Deploy** roda, avisa no
resumo e sai sem erro.

## 2. Chave de deploy só deste projeto

Gere um par de chaves novo, só para a Pixelzada (não reaproveite a do Cortexplor:
assim, revogar uma não derruba a outra):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/pixelzada_deploy -C "deploy-pixelzada" -N ""
```

- A **pública** (`~/.ssh/pixelzada_deploy.pub`) vai no painel da hospedagem, em
  Acesso SSH > Chaves SSH.
- A **privada** vai no GitHub como secret `HOSTINGER_SSH_KEY` (item 3).

## 3. Secrets no GitHub

Em **Settings > Secrets and variables > Actions > New repository secret**:

| Secret | O que é | Onde conseguir |
|---|---|---|
| `HOSTINGER_SSH_KEY` | a chave privada de deploy | `~/.ssh/pixelzada_deploy` |
| `UNSPLASH_ACCESS_KEY` | banco de imagens (provisório) | unsplash.com/developers |
| `PEXELS_API_KEY` | banco de imagens (reserva) | pexels.com/api |

## 4. Conferir as fontes RSS

Rode o workflow **Coletar** na mão (Actions > Coletar > Run workflow). O log
mostra cada feed que falhou com `!`. Corrija ou remova esses em `sources.rss`.
A lista foi montada sem acesso à internet e nenhum feed foi testado ainda.

## 5. Ligar a publicação automática (modo Routine)

1. Instale o app do Claude no GitHub para o repositório `pixelzada`.
2. Preencha `publishing.launch_date` com a data do primeiro deploy. É ela que
   move o ramp (5, 6, 8 e 10 matérias por dia).
3. Crie a Routine em <https://claude.ai/code/routines>, rodando 30 minutos depois
   de cada coleta (07h30, 12h30 e 18h30) e seguindo
   `.claude/skills/redacao-diaria/SKILL.md`.

O push da Routine aciona o **Finalizar** (imagem, gate e build), que chama o
**Deploy**.

---

## 6. Google Analytics 4 e Search Console

```yaml
analytics:
  ga4_id: "G-XXXXXXXXXX"
  search_console_verification: ""
  ga4_property_id: "123456789"
  search_console_site: "https://pixelzada.com.br/"
```

No Search Console, envie `https://pixelzada.com.br/sitemap-pt.xml`.

Para o workflow **Métricas** (semanal), crie uma conta de serviço no Google Cloud
com leitura no GA4 e no Search Console e cole o JSON dela no secret
`GA_SEARCH_CONSOLE_CREDENTIALS`.

## 7. AdSense (começo de novembro)

O plano é pedir no começo de novembro de 2026. O `run status` avisa quando o site
tem lastro (30 matérias, 21 dias no ar, gate acima de 70%). Antes de pedir,
`client_id` pode entrar no config para a verificação do Google; os anúncios só
aparecem com `enabled: true`.

## 8. E-mail

Criar `contato@pixelzada.com.br`. Ele aparece no rodapé e nas páginas
institucionais.

## 9. Identidade visual

Quando a identidade ficar pronta, troque:

- as cores em `brand:` no `site.config.yaml`;
- os arquivos em `assets/logo/` (mesmos nomes, ou ajuste `brand.logo`);
- as webfonts em `assets/fonts/` e `assets/css/fonts.css`, e `brand.fonts`;
- o fundo decorativo da capa em `templates/partials/sky.html` (ainda é a rede de
  nós do Cortexplor).

---

## Checagem rápida antes de abrir ao público

```bash
python scripts/tools/selfcheck.py
python -m scripts.pipeline.run status
python -m http.server 4173
```

- [ ] `launch_date` preenchido
- [ ] `deploy.enabled: true` e o site respondendo em `/pt/`
- [ ] GA4 e Search Console ativos
- [ ] páginas institucionais revisadas (`/pt/sobre/`, `/pt/privacidade/`,
      `/pt/contato/`, `/pt/termos/`)
- [ ] `contato@pixelzada.com.br` funcionando

## Publicação ao longo do dia

A coleta roda três vezes por dia (07h, 12h e 18h) e a Routine 30 minutos depois
de cada uma. Três pontos andam juntos:

1. `publishing.run_hours` no `site.config.yaml`.
2. Os `cron` do workflow **Coletar** (em UTC; Brasília é UTC-3).
3. O horário da Routine.

O teto diário (`publishing.ramp`) é dividido entre as rodadas que faltam no dia.
