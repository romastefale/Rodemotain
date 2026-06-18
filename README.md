# Rodemotain Bot Moderador

Rodemotain é um bot de moderação para grupos e supergrupos do Telegram. Ele foi pensado para ser operado principalmente por DM, usando botões, seleção de grupo e confirmação antes de ações sensíveis.

O bot pode moderar mais de um grupo. Depois que ele conhece os grupos onde está presente, o operador abre o painel no privado, escolhe o grupo desejado e executa as ações disponíveis para aquele grupo.

## Como começar

1. Crie o bot no BotFather e copie o token.
2. Coloque o bot como administrador nos grupos que ele deve moderar.
3. Dê ao bot as permissões de administrador necessárias para as funções que você pretende usar.
4. Configure as variáveis no Railway ou no arquivo `.env` local.
5. Faça o deploy.
6. Abra o privado do bot e envie `/start`.
7. Envie `/tigrao` para abrir o painel.
8. Selecione o grupo e use os botões.

O bot não responde livremente no grupo para evitar poluição. O painel principal é aberto no privado do operador autorizado.

## Comandos disponíveis

`/start` mostra uma apresentação curta do bot e confirma se ele está online.

`/help` lista os comandos e os recursos disponíveis.

`/tigrao` abre o painel de moderação. Em DM, o painel abre diretamente. Em grupo, o bot tenta enviar o painel no privado do usuário autorizado.

`/captcha código` é usado por novos membros quando o grupo está protegido por captcha de entrada.

## Quem pode usar o painel

Somente os usuários definidos na variável `TIGRAO_BOT_ACCESS_USER_IDS` podem abrir e operar o painel.

Exemplo:

```env
TIGRAO_BOT_ACCESS_USER_IDS=123456789,987654321
```

Cada número deve ser o Telegram ID de uma pessoa autorizada. Se alguém não autorizado enviar `/start` ou `/help`, o bot responde apenas que é privado. Se tentar usar `/tigrao`, não abre o painel.

## Permissões que o bot precisa no grupo

Para usar o bot com força total, coloque-o como administrador e marque as permissões compatíveis com o que você quer permitir:

- apagar mensagens;
- restringir membros;
- banir usuários;
- convidar usuários e gerenciar solicitações de entrada;
- fixar mensagens;
- gerenciar tópicos;
- alterar informações do grupo;
- promover administradores, se for usar promoção/rebaixamento;
- gerenciar chamadas, stories, tags ou recursos avançados quando o Telegram disponibilizar isso no grupo.

Se uma função falhar, normalmente o motivo é falta de permissão do bot naquele grupo.

## Como o painel funciona

Abra o privado do bot e envie:

```text
/tigrao
```

O painel começa com a opção de selecionar grupo. Depois de selecionar um grupo, aparecem as áreas principais:

- logs;
- solicitações de entrada;
- ações do grupo;
- DDX hard;
- reações.

Ações sensíveis não são executadas no primeiro toque. O bot prepara a ação, mostra um resumo e exige o botão **Confirmar**. Isso vale para ações como banir, mutar, apagar, alterar título, alterar foto, fechar grupo, revogar link e outras operações administrativas.

Use **Voltar** para retornar à tela anterior e **Fechar** para encerrar o painel.

## Como registrar grupos no painel

A lista de grupos é preenchida quando o bot recebe algum update daquele grupo.

Depois de adicionar o bot como administrador, faça uma destas ações:

- envie uma mensagem qualquer no grupo;
- envie `/tigrao` no grupo com uma conta autorizada;
- gere uma solicitação de entrada no grupo;
- use algum evento normal do grupo que chegue ao bot.

Depois disso, o grupo deve aparecer na seleção do painel por DM.

## Solicitações de entrada

A área de solicitações permite ver usuários pendentes, aceitar por ID, recusar por ID, criar link com solicitação de entrada e configurar automações.

O bot também pode trabalhar com proteção de entrada por captcha, anti-raid e fila de aprovação.

O Mini App de entrada, quando configurado, abre uma tela como esta:

```text
Rodemotain
Solicitação de entrada

Selecione o grupo
Confirme as regras
Resolva o captcha
Envie a solicitação
```

A URL padrão do Mini App é:

```text
https://seu-dominio.up.railway.app/join-request
```

No Railway, se `BASE_URL` estiver correto, o bot consegue usar automaticamente `BASE_URL + /join-request`. Se quiser definir manualmente, use:

```env
TIGRAO_JOIN_REQUEST_WEBAPP_URL=https://seu-dominio.up.railway.app/join-request
```

Não coloque o webhook nessa variável. Ela deve apontar para a tela visual do Mini App, não para `/telegram/webhook`.

## DDX hard

DDX hard é o filtro textual que apaga mensagens quando elas batem em termos cadastrados.

Pelo painel, entre em **DDX hard** e use:

- ativar DDX;
- desativar DDX;
- adicionar filtro;
- listar filtros;
- remover filtro.

Exemplos de filtro:

```text
spam
link proibido | 30m
golpe | 7d
termo sensível | permanente
```

Quando há tempo definido, o filtro expira automaticamente. Quando é permanente, permanece ativo até ser removido.

## Ações de moderação

Na área **Ações do grupo**, o bot pode executar ações leves, médias e destrutivas, sempre conforme as permissões disponíveis no grupo.

Entre as ações disponíveis estão:

- banir usuário;
- banir com tempo livre;
- desbanir usuário;
- mutar por tempo fixo;
- mutar com tempo livre;
- desmutar usuário;
- apagar mensagem por ID ou link;
- apagar lote de mensagens;
- fechar grupo;
- reabrir grupo;
- fixar mensagem;
- desfixar mensagem;
- limpar fixados;
- alterar título;
- alterar descrição;
- alterar ou remover foto do grupo;
- promover administrador;
- rebaixar administrador;
- definir título customizado de administrador;
- banir sender chat ou canal;
- desbanir sender chat ou canal;
- gerenciar links de convite;
- gerenciar tópicos e fórum;
- definir tag real de membro;
- adicionar, listar e limpar advertências;
- configurar anti-flood;
- configurar anti-raid;
- configurar captcha;
- auditar administradores e bots;
- remover reação específica;
- remover reações recentes.

Para tempos livres, use formatos como:

```text
123456789 | 30m
123456789 | 1h30m
123456789 | 7d
123456789 | permanente
```

Para purge, use exemplos como:

```text
10-25
10,11,12,13
https://t.me/c/1234567890/55
```

## Links de convite

O bot pode exportar o link primário, criar link completo, editar link e revogar link.

Essa função depende de permissão para convidar usuários. Quando o link for criado com solicitação de entrada, os usuários não entram direto; ficam pendentes para aprovação, recusa, captcha, fila ou Mini App, conforme a configuração do grupo.

## Proteções automáticas

O bot possui proteções de entrada e comportamento:

- captcha para novos membros;
- anti-raid para picos de entrada;
- anti-flood para excesso de mensagens;
- warnings e reincidência;
- DDX hard para termos proibidos.

Essas proteções devem ser configuradas por grupo. Um grupo pode ter regras diferentes de outro.

## Logs

A área **Logs** mostra registros úteis para acompanhar o que aconteceu no bot:

- moderação;
- uso;
- entradas;
- erros.

Use os logs para confirmar se uma ação foi executada, se alguém tentou usar o bot, se houve erro de permissão ou se houve evento de entrada.

## Configuração no Railway

As variáveis mínimas para deploy são:

```env
TELEGRAM_BOT_TOKEN=token_do_bot
TIGRAO_BOT_ACCESS_USER_IDS=seu_id_telegram
WEBHOOK_SECRET=um_segredo_forte
RUN_POLLING=false
SET_WEBHOOK_ON_STARTUP=true
```

Recomendado deixar também:

```env
WEBHOOK_PATH=/telegram/webhook
```

Se quiser definir o domínio manualmente:

```env
BASE_URL=https://seu-servico.up.railway.app
```

Se `BASE_URL` não for definido, o bot tenta usar o domínio público fornecido pelo Railway.

Para persistência, crie um volume no Railway e monte em:

```text
/data
```

Se o volume estiver em `/data`, o bot usa esse caminho para guardar o banco SQLite. Se você quiser deixar explícito:

```env
DATA_DIR=/data
DATABASE_URL=sqlite:////data/moderador.sqlite3
```

## Healthcheck

O healthcheck do serviço é:

```text
/healthz
```

Depois do deploy, teste no navegador:

```text
https://seu-dominio.up.railway.app/healthz
```

A resposta correta é:

```json
{"status":"ok"}
```

Se `/healthz` responde, o servidor web subiu. Se o bot não responde no Telegram, verifique webhook, token, segredo, variáveis e permissões.

## Webhook

O webhook padrão é:

```text
/telegram/webhook
```

Com domínio Railway, fica assim:

```text
https://seu-dominio.up.railway.app/telegram/webhook
```

O bot registra o webhook automaticamente quando `SET_WEBHOOK_ON_STARTUP=true` e `RUN_POLLING=false`.

## Rodar localmente

Para teste local por polling:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.bootstrap
```

No `.env` local, use:

```env
RUN_POLLING=true
SET_WEBHOOK_ON_STARTUP=false
```

No Railway, use webhook:

```env
RUN_POLLING=false
SET_WEBHOOK_ON_STARTUP=true
```

## O que fazer se o bot não responder

Primeiro, abra:

```text
https://seu-dominio.up.railway.app/healthz
```

Se não responder `{"status":"ok"}`, o problema está no deploy.

Se `/healthz` responder, verifique:

- se `TELEGRAM_BOT_TOKEN` está correto;
- se `BASE_URL` não está com aspas, espaço ou apóstrofo no final;
- se `WEBHOOK_SECRET` está preenchido;
- se `RUN_POLLING=false` no Railway;
- se `SET_WEBHOOK_ON_STARTUP=true`;
- se seu ID está em `TIGRAO_BOT_ACCESS_USER_IDS`;
- se você está falando com o bot correto;
- se o bot recebeu o deploy mais recente;
- se o bot tem permissão de administrador no grupo.

Se o log mostrar `Update ... is not handled`, significa que o Telegram chegou até o servidor, mas aquele tipo de update não foi tratado pelo bot. Para os comandos principais, teste `/start` e `/help` no privado.

## Segurança operacional

Não coloque pessoas aleatórias em `TIGRAO_BOT_ACCESS_USER_IDS`.

Não compartilhe `TELEGRAM_BOT_TOKEN`.

Não use `WEBHOOK_SECRET` fraco ou igual ao token.

Antes de usar ações destrutivas em grupo grande, teste em um grupo pequeno.

Confirme sempre o grupo selecionado no painel antes de executar ban, mute, purge, links, foto, título, descrição ou permissões.

## Nomes técnicos mantidos

A interface visível usa o nome Rodemotain. Alguns nomes técnicos continuam com `TIGRAO`, como:

```text
/tigrao
TIGRAO_BOT_ACCESS_USER_IDS
TIGRAO_JOIN_REQUEST_WEBAPP_URL
```

Esses nomes foram mantidos para não quebrar compatibilidade com o deploy, variáveis e callbacks internos.


## Mini App de entrada

A tela `/join-request` usa automaticamente a foto de perfil pública do bot no Telegram como ícone. A seleção de grupo aparece em botões próprios do Rodemotain, sem depender dos círculos nativos de seleção do navegador.

## Navegação do painel

O painel do Rodemotain é organizado por categorias para evitar listas longas de botões. Depois de selecionar um grupo no `/tigrao`, use as categorias principais:

- 📥 Entrada: solicitações de entrada, fila, links com solicitação e autorizações.
- 👤 Usuários: ban, mute, desmute, advertências e tag de membro.
- 💬 Mensagens: apagar mensagem, purge, fixar e desfixar.
- 👑 Admins: auditoria, promover/rebaixar e título customizado.
- 🔗 Links: criar, editar, exportar e revogar links de convite.
- 🧩 Tópicos: funções de fórum e tópico geral.
- 🎛️ Grupo: título, descrição, foto e fechamento/reabertura do grupo.
- 🛡️ Proteções: anti-flood, anti-raid, captcha, DDX e status.
- ⚛️ Reações: remoção de reações.
- 📊 Logs / 🧾 Auditoria: consulta de registros, permissões e estado do grupo.

Use `⬅️ Categorias` para voltar ao menu de categorias e `⬅️ Grupo` para voltar ao painel do grupo selecionado. Ações sensíveis continuam pedindo confirmação antes da execução.
