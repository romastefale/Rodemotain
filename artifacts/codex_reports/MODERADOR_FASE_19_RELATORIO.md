# MODERADOR FASE 19 — Mini App de entrada com seleção de grupo

Base real usada: `tigrao-moderador-bot-fase18.zip`.

## Objetivo
Criar a tela visual `/join-request` para Join Request Mini App com opção de selecionar o grupo, porque o mesmo bot pode atuar em mais de um grupo/supergrupo.

## Implementado

- Criada tela HTML/CSS/JS em `app/static/`:
  - `join-request.html`
  - `join-request.css`
  - `join-request.js`
- Criada rota pública de tela:
  - `GET /join-request`
- Criado endpoint de grupos para a tela:
  - `POST /telegram/join-request/groups`
- O endpoint lista grupos registrados pelo bot em `tigrao_groups`.
- A lista exige `WEBHOOK_SECRET` interno ou `Telegram.WebApp.initData` válido.
- A tela mostra seletor de grupo, confirmações obrigatórias e captcha simples local.
- A tela envia a resolução como `queue`, não como aprovação automática.
- O endpoint `/telegram/join-request-query` aceita `selected_chat_id`.
- O backend valida que o grupo selecionado corresponde ao `query_id` real salvo no banco.
- Se o usuário selecionar grupo diferente da solicitação real, a resolução é bloqueada com HTTP 409.
- `TIGRAO_JOIN_REQUEST_WEBAPP_URL` agora usa fallback automático para `BASE_URL + /join-request`.
- O runtime de join request passa a salvar `query_id` no banco.
- Quando o Mini App é enviado com sucesso, o runtime consome o fluxo e não duplica captcha/autoaceite no mesmo update.

## Segurança aplicada

- A seleção de grupo é visual e validada no backend.
- O usuário não consegue trocar de grupo apenas mudando o seletor.
- O endpoint de grupos não expõe grupos sem secret ou initData assinado quando `WEBHOOK_SECRET` está configurado.
- Foi criada validação HMAC de `Telegram.WebApp.initData` em `app/bot/telegram_webapp.py`.

## Validação

Executado no pacote final:

```bash
python -m compileall -q app tests
pytest -q
```

Resultado:

```text
72 passed
```

## Limites honestos

- A tela depende de `query_id` real vindo do Telegram para resolver uma solicitação de entrada real.
- Fora do Telegram, a página abre, mas não consegue resolver a solicitação sem `query_id`.
- O captcha da tela é simples e local; o captcha persistente por DM do bot continua existindo como proteção separada.
- Teste real com token/Railway/Telegram ainda deve ser feito.
