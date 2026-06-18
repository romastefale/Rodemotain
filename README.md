# Tigrão Moderador Bot

Repositório isolado apenas para o bot moderador Tigrão FSM. Este pacote foi separado do TR4 musical e não contém comandos, serviços, modelos, templates ou dependências musicais.

## O que foi mantido

- Painel `/tigrao` por DM para owner/moderadores.
- Seleção de grupos conhecidos pelo bot.
- Verificação de permissões do bot no grupo.
- Solicitações de entrada e autoaceite por ID.
- DDX hard por filtro textual.
- Ações destrutivas com confirmação explícita: ban, unban, mute, unmute e apagar mensagem.
- Logs de moderação, uso, entrada e erro.
- Healthcheck `/healthz` puro para Railway.

## O que foi removido

- Todo o diretório musical do TR4.
- Last.fm, Spotify, Canvas, letras, capas, cards, mosaico, tnow, tly, radiofm, web app musical.
- Import quebrado de `app.bot.owner_manual_register`.
- Dependência de `app.bot.music_groups`; foi substituída por `app.bot.group_registry`.
- Entradas de log musical no painel.

## Variáveis principais

Copie `.env.example` e configure. O pacote moderador não usa mais flags para ligar/desligar painel, ações destrutivas ou DDX: as funções reais ficam ativas por padrão. A variável funcional de acesso ao painel é uma só:

```env
TELEGRAM_BOT_TOKEN=123456:token_do_bot
TIGRAO_BOT_ACCESS_USER_IDS=123456789,987654321
# BASE_URL=https://seu-servico.up.railway.app
WEBHOOK_SECRET=troque-este-segredo
```

`TIGRAO_BOT_ACCESS_USER_IDS` define quem pode abrir e operar o `/tigrao`. Variáveis antigas como `CODE_OWNER_IDS`, `OWNER_IDS`, `TIGRAO_FSM_MODERATOR_IDS` e `MODERATOR_IDS` ainda são aceitas como aliases para não quebrar deploys antigos, mas a configuração nova deve usar apenas `TIGRAO_BOT_ACCESS_USER_IDS`.

Para Railway, deixe `RUN_POLLING=false`. `BASE_URL` é opcional quando o Railway fornecer `RAILWAY_PUBLIC_DOMAIN` ou `RAILWAY_STATIC_URL`; defina `BASE_URL` manualmente apenas para sobrescrever o domínio detectado. Para rodar localmente por polling, use `RUN_POLLING=true`.

## Rodar localmente

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.bootstrap
```

## Deploy Railway

O projeto usa `Dockerfile` e `railway.toml`. O start command é:

```bash
python -m app.bootstrap
```

O healthcheck é:

```text
/healthz
```

## Observação de operação

A lista de grupos é preenchida quando o bot recebe updates de grupos ou solicitações de entrada. Depois de adicionar o bot a um grupo, envie qualquer mensagem no grupo ou use `/tigrao` no grupo para o bot registrar o chat e disponibilizá-lo no painel por DM.

## Avanço aplicado nesta versão

Além da separação do TR4 musical, esta versão reforça o bot moderador isolado nos pontos operacionais abaixo:

- O modo polling também registra grupos conhecidos pelo bot, sem depender do webhook.
- O modo polling também processa `chat_join_request`, mantendo autoaceite e aprovação por ID fora do endpoint HTTP.
- O DDX hard também roda em mensagens de grupo no polling: só apaga se houver filtro explícito ativo e o bot tiver permissão de apagar mensagens.
- A ação “Apagar mensagem” aceita tanto `message_id` numérico quanto link Telegram `t.me`, incluindo links privados `/c/<chat>/<mensagem>` e links de tópicos `/c/<chat>/<tópico>/<mensagem>`.
- Links privados de outro grupo são recusados antes da confirmação para evitar apagar mensagem do grupo errado.
- Foi adicionado `pytest.ini` para permitir rodar `pytest -q` diretamente na raiz do projeto.

Validação local executada nesta entrega:

```bash
python -m compileall -q app tests
pytest -q
```

Resultado local: `8 passed`.

Observação de segurança: ações destrutivas e DDX hard ficam disponíveis por padrão neste pacote moderador. A proteção operacional continua sendo feita por escopo de acesso ao painel, confirmação explícita, validação de permissões do bot no grupo, bloqueio contra alvo protegido e exigência de filtro DDX cadastrado.

## Fase 07 — ativação padrão

Alteração aplicada: painel, seleção de grupos, solicitações de entrada, autoaceite por ID, ações destrutivas com confirmação, apagar mensagem por ID/link, DDX hard e logs ficam ativos por padrão. A única variável de autorização do painel passa a ser `TIGRAO_BOT_ACCESS_USER_IDS`.

O módulo de reações ainda está reservado como stub e não foi exposto como função real nesta fase, para não apresentar botão que ainda não executa ação efetiva.

## Fase 10 — Funções novas de moderação

O painel inclui funções novas com revalidação de permissões no momento da execução:

- ban com tempo livre: `user_id | tempo`;
- mute com tempo livre: `user_id | tempo`;
- purge de 1 a 100 mensagens por IDs, links `t.me` ou intervalo `10-25`;
- lockdown/unlock do grupo por permissões padrão;
- fixar, desfixar e limpar fixados;
- alterar título e descrição do grupo;
- remover reação específica e remover reações recentes de um usuário/chat ator;
- auditar administradores, incluindo bots administradores quando a Bot API/wrapper aceitar `return_bots=True`.

As funções continuam restritas aos usuários definidos em `TIGRAO_BOT_ACCESS_USER_IDS`.

## Fase 11 — Auditoria e revisão de erros

A Fase 11 revisou navegação, botões e confirmação das funções novas da Fase 10.

Mudanças principais:

- ações avançadas novas não executam mais imediatamente após texto enviado na DM;
- `bantime`, `mutetime`, `purge`, `pin`, `unpin`, `settitle`, `setdesc`, `react1` e `reactall` agora exigem botão `Confirmar`;
- `lock`, `unlock` e `unpinall` também exigem confirmação;
- `Ver pendentes 2h` agora é somente consulta, sem ativar aceitação por ID automaticamente;
- `Voltar` limpa ações pendentes e retorna à superfície correta quando possível;
- `_safe_edit` ganhou fallback para mensagem de painel antiga, apagada ou já modificada;
- purge aceita intervalos com espaços, por exemplo `10 - 12`.

Validação local da fase:

```bash
python -m compileall -q app tests
pytest -q
```

Resultado: `34 passed`.

## Fase 15 — auditoria de segurança e navegação

Aplicada revisão sobre a Fase14. A alteração de foto do grupo agora segue o padrão do painel: receber a foto apenas prepara a ação; a foto só é aplicada depois do botão **Confirmar**. O captcha passou a persistir e respeitar `max_attempts` por desafio. O anti-raid agora consome o fluxo quando acionado, inclusive nos modos `queue` e `lock`, evitando autoaceite/captcha depois da detecção de raid.

Validação local da fase: `54 passed`.


## Railway Fase17

No Railway, `BASE_URL` é opcional quando `RAILWAY_PUBLIC_DOMAIN` ou `RAILWAY_STATIC_URL` estiver disponível. O bot normaliza o domínio para `https://...`. Para persistência, `DATA_DIR` é opcional quando `RAILWAY_VOLUME_MOUNT_PATH` estiver disponível; caso contrário, use volume em `/data`. O healthcheck configurado é `/healthz`.
