# MODERADOR FASE 22 — Ajuste visual do Web App e ícone do bot

Base usada: `tigrao-moderador-bot-fase21.zip`.

## Alterações aplicadas

- A tela `/join-request` passou a usar a foto de perfil pública do próprio bot no Telegram como ícone da interface.
- Foi criado o endpoint `GET /telegram/bot-icon`.
- O endpoint baixa a foto via Bot API HTTP (`getMe`, `getUserProfilePhotos`, `getFile` e download pelo endpoint `/file/bot...`) e usa cache local no `DATA_DIR`.
- Se não houver token, foto ou acesso à Bot API, a interface usa um SVG seguro com a inicial `R`.
- A seleção de grupo deixou de depender visualmente do controle nativo do navegador e passou a usar botões customizados com `role="radio"`.
- As confirmações obrigatórias usam marcadores customizados (`choice-dot`) e escondem o checkbox nativo, eliminando artefatos visuais ao redor do círculo.
- O `<select id="groupSelect">` foi mantido oculto para compatibilidade e estado interno, mas a navegação visível usa botões.

## Validação

```bash
python -m compileall -q app tests
pytest -q
```

Resultado local: `77 passed`.

## Observação

Para a interface usar a foto real, o bot precisa ter foto de perfil configurada no Telegram e o container precisa conseguir acessar a Bot API. Sem isso, o fallback visual continua funcionando.
