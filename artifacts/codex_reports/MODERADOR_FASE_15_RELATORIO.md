# MODERADOR FASE 15 — Auditoria de segurança, navegação e confirmação

Base factual usada: `tigrao-moderador-bot-fase14.zip`.

## Objetivo
Auditar a implementação das funções novas da Fase14 e corrigir pontos que fugiam do padrão de eficiência, segurança, navegação e confirmação explícita.

## Correções aplicadas

1. Alteração de foto do grupo
   - Antes: a foto era aplicada imediatamente quando o owner/moderador enviava a imagem por DM.
   - Agora: o envio da foto apenas cria `pending_advanced_action` com `file_id` e exibe o botão `Confirmar`.
   - A foto só é baixada e aplicada no callback `Confirmar`.
   - Resultado: segue o mesmo padrão seguro das demais ações administrativas/destrutivas.

2. Anti-raid
   - Antes: quando a regra era `queue` ou `lock`, o runtime podia continuar para captcha/autoaceite depois de detectar raid.
   - Agora: qualquer ação anti-raid acionada consome o update e impede continuação automática do fluxo.
   - `decline` recusa, `lock` fecha o grupo e deixa a solicitação em fila, `queue` mantém a solicitação pendente.

3. Captcha
   - Antes: `max_attempts` configurado no painel era salvo na configuração, mas a verificação por `/captcha` usava 3 fixo.
   - Agora: o desafio armazena `max_attempts` no banco, com migração idempotente.
   - A verificação usa o valor salvo no desafio.
   - Se exceder tentativas, o bot tenta recusar a solicitação com `decline_chat_join_request` quando tiver permissão.

## Testes empíricos adicionados

Arquivo novo:

`tests/test_tigrao_moderador_phase15_audit.py`

Cobertura adicionada:

- Foto recebida em DM prepara confirmação e não chama API do Telegram antes do botão.
- Confirmar foto baixa o arquivo e chama `set_chat_photo`.
- Captcha usa `max_attempts` salvo por desafio.
- Anti-raid `queue` consome o update.
- Anti-raid `lock` fecha o grupo e consome o update.

## Validação

```bash
python -m compileall -q app tests
pytest -q
```

Resultado final:

`54 passed`

## Limite não testado

Não houve teste com token real no Telegram/Railway. A validação foi empírica por testes locais com bots falsos e conferência de chamadas previstas à API.
