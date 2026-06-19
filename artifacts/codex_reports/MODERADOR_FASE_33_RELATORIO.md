# MODERADOR FASE 33 — Interface sucinta e validação API

Base: Fase32.

## Alterações

- Textos do `/start` e `/help` foram encurtados.
- Tela de grupo selecionado foi reduzida para status, permissões ativas e permissões ausentes.
- Menus de entrada, categorias, subcategorias, confirmações e resultados foram reescritos com frases curtas.
- Mensagens de resultado agora usam `✅ Concluído` ou `⚠️ Não concluído`.
- Erros Telegram comuns são humanizados na saída do painel, incluindo `RIGHT_FORBIDDEN`, `USER_NOT_PARTICIPANT` e `CHAT_ADMIN_REQUIRED`.
- Prompts de ações avançadas foram simplificados e passaram a incentivar campos por quebra de linha.
- Parsers agora aceitam quebra de linha em mais entradas operacionais, mantendo o formato antigo com `|` por compatibilidade:
  - título customizado de admin;
  - tag/warn por usuário;
  - criação e edição de link;
  - anti-flood, anti-raid e captcha.

## Validação

- `python -m compileall -q app tests`
- `pytest -q`

Resultado: 108 passed.
