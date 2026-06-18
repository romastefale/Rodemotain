# MODERADOR FASE 31 — Mini App com seletor de grupo e viewport travada

## Base

Aplicado sobre o ZIP real `tigrao-moderador-bot-fase30.zip`.

## Alterações aplicadas

- O Mini App `/join-request` deixou de mostrar os grupos em sequência visual fixa.
- A seleção de grupo agora usa um botão/seletor customizado que abre um menu `listbox` expansível.
- O menu de grupos tem altura máxima e rolagem interna, evitando uma tela muito longa quando o bot conhece muitos grupos.
- O seletor mantém o `select#groupSelect` oculto como fonte de estado/compatibilidade, mas a interface pública usa `#groupPickerButton` e `#groupMenu`.
- A viewport do Mini App foi ajustada para evitar zoom e manter a interface preenchendo a tela de exibição:
  - `maximum-scale=1`
  - `user-scalable=no`
  - `viewport-fit=cover`
  - CSS `--app-height` controlado por JS
  - uso de `Telegram.WebApp.viewportHeight`
  - atualização em `viewportChanged`
  - `tg.expand()`
  - `tg.disableVerticalSwipes()` quando disponível
  - inputs com `font-size: 16px` para evitar zoom automático em iOS.

## Arquivos principais alterados

- `app/static/join-request.html`
- `app/static/join-request.css`
- `app/static/join-request.js`
- `tests/test_tigrao_moderador_phase22_webapp_ui.py`
- `tests/test_tigrao_moderador_phase31_webapp_dropdown_viewport.py`

## Validação

```bash
python -m compileall -q app tests
pytest -q
```

Resultado local: `102 passed`.
