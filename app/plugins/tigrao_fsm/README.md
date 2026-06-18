# Tigrão FSM Moderador

Módulo isolado do painel de moderação. Não depende de comandos externos ao escopo de administração do grupo.

Submódulos principais:

- `state.py`: sessões temporárias do painel.
- `keyboards.py`: callbacks curtos `tgf:`.
- `routers/panel.py`: painel `/tigrao` por DM.
- `runtime/`: tratamento pré-dispatch de solicitações de entrada e DDX.
- `storage.py`: persistência dos registros de moderação.
