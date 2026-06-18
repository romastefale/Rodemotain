# MODERADOR FASE 26 — Navegação por categorias, subcategorias e agrupamento visual

Base: `tigrao-moderador-bot-fase25.zip`.

## Objetivo

Reorganizar o painel do Rodemotain para reduzir sequências longas de botões, deixar a navegação por categorias e subcategorias mais intuitiva, e agrupar visualmente ações positivas/restauradoras antes de ações destrutivas/restritivas.

## Alterações aplicadas

- O menu principal do grupo agora agrupa primeiro categorias com intenção positiva/consulta/restauração, usando prefixo visual `✅`.
- Categorias restritivas/destrutivas foram agrupadas juntas com prefixos `🚫`, `🚨` e `🧨`.
- As categorias deixaram de abrir listas longas de funções diretamente.
- Foram adicionadas subcategorias intermediárias para usuários, mensagens, admins, links, tópicos, grupo, proteções e reações.
- Subcategorias exibem as ações finais e mantêm botões de retorno claros:
  - `⬅️ Subcategorias`
  - `⬅️ Categorias`
  - `⬅️ Grupo`
  - `✖️ Fechar`
- As ações sensíveis continuam com fluxo de confirmação e validação antes da execução.

## Exemplos da nova navegação

### Menu de categorias

- 📥 Entrada / 📊 Logs
- ✅ 👤 Usuários / ✅ 🔗 Links
- ✅ 🧩 Tópicos / 🧾 Auditoria
- 🚫 💬 Mensagens / 🚫 👑 Admins
- 🚫 🎛️ Grupo / 🚨 🛡️ Proteções
- 🧨 DDX hard / ⚛️ Reações

### Usuários

- ✅ Liberar/restaurar
- 🚫 Restringir usuário
- ⚠️ Warnings e tags

### Mensagens

- ✅ Fixar/organizar
- 🗑️ Apagar/limpar

### Tópicos

- ✅ Reabrir/reexibir
- ➕ Criar/editar
- 🚫 Fechar/ocultar
- 🗑️ Apagar/limpar

## Arquivos alterados

- `app/plugins/tigrao_fsm/keyboards.py`
- `app/plugins/tigrao_fsm/routers/panel.py`
- `tests/test_tigrao_moderador_phase10.py`
- `tests/test_tigrao_moderador_phase25_categorized_nav.py`
- `tests/test_tigrao_moderador_phase26_navigation_subcategories.py`

## Validação

```bash
python -m compileall -q app tests
pytest -q
```

Resultado: `90 passed`.
