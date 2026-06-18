# MODERADOR FASE 17 — Railway automático e healthcheck

Base usada: `tigrao-moderador-bot-fase16.zip`.

## Alterações aplicadas

1. `BASE_URL` agora é resolvido automaticamente no Railway quando não for informado manualmente:
   - prioridade 1: `BASE_URL` / `TR3_BASE_URL`;
   - prioridade 2: `RAILWAY_PUBLIC_DOMAIN`;
   - prioridade 3: `RAILWAY_STATIC_URL`.

2. Domínios públicos sem esquema são normalizados para `https://...`.

3. `DATA_DIR` agora usa fallback do Railway:
   - prioridade 1: `DATA_DIR`;
   - prioridade 2: `RAILWAY_VOLUME_MOUNT_PATH`;
   - prioridade 3: `/data`;
   - prioridade 4: `.data` local e diretórios locais graváveis.

4. `DATABASE_URL` continua opcional. Quando não informada, é derivada automaticamente de `DATA_DIR`.

5. `.env.example` e `README.md` foram atualizados para refletir que `BASE_URL`, `DATA_DIR` e `DATABASE_URL` podem ser omitidos em deploy Railway quando as variáveis nativas existem.

6. `/healthz` foi conferido:
   - rota existente em `app/main.py`;
   - retorna `{"status": "ok"}`;
   - `railway.toml` aponta `healthcheckPath = "/healthz"`.

## Testes adicionados

Arquivo: `tests/test_tigrao_moderador_phase17_railway.py`.

Cobertura:
- `RAILWAY_PUBLIC_DOMAIN` vira `BASE_URL` com `https://`;
- `BASE_URL` manual tem prioridade sobre domínio Railway;
- `RAILWAY_VOLUME_MOUNT_PATH` vira `DATA_DIR`;
- `DATABASE_URL` SQLite é derivada automaticamente do volume.

## Validação

```bash
python -m compileall -q app tests
pytest -q
```

Resultado local:

```text
63 passed
```

## Limite

Não houve teste real no Railway com token Telegram. A validação foi local e empírica sobre resolução de configuração, healthcheck estático e suíte do projeto.
