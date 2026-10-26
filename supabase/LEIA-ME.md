# Conectar o ControlAI ao seu Supabase

Projeto: `https://uyeopkssqzxjaooqjehl.supabase.co`.

A URL e a chave **pública** fornecidas estão em `config.json`. Nenhuma chave secreta ou senha é necessária no código. A chave pública identifica o projeto, mas não concede acesso aos dados: login, autorização e funções no banco são obrigatórios.

## Faça no painel Supabase

1. Abra **SQL Editor → New query**.
2. Copie todo o conteúdo de [setup.sql](setup.sql), cole e clique **Run**. Esse é o SQL de configuração do banco, não o antigo código de ativação do app. Ele cria objetos com prefixo `controlai_`, ativa RLS e autoriza `arthurlopescorporativo@gmail.com` como administrador. Não apaga tabelas preexistentes.
3. Em **Authentication → Users → Add user → Create new user**, crie sua conta com `arthurlopescorporativo@gmail.com`. Defina a senha ali, com pelo menos 12 caracteres, e marque a confirmação do e-mail se essa opção aparecer. Não envie a senha no chat. Não use o botão de convite por e-mail sem configurar antes o serviço de envio e os endereços de redirecionamento.
4. Entre no app com esse e-mail e senha. A opção `setup-code` não é usada no modo Supabase.

Se a sua conta já existe no Authentication, não crie outra; use a senha existente. Se houver erro SQL, a transação é revertida: não remova regras de segurança para tentar contornar o erro. Compartilhe apenas o texto do erro, sem senhas/tokens.

## Usuários de apoio

Depois de entrar, em **Usuários e histórico**, autorize os e-mails dos outros dois operadores. Depois crie cada conta em **Authentication → Users**. Com apenas a chave pública, o app não pode criar contas administrativas no serviço Auth nem enviar convites em nome do projeto. A interface informa essa etapa, sem simular convite enviado. Desativar o acesso no app bloqueia as operações imediatamente pelas funções do banco, mesmo com um token Auth ainda válido. O limite de três pessoas é aplicado no banco.

Ajuste também as configurações de segurança e política de senhas no Supabase antes do uso. Recuperação de senha por e-mail e redirecionamentos ainda não foram integrados ao app.

## Iniciar o app

```sh
cd /workspace/ctrlestoque
python3 server.py
```

O backend padrão agora é **Supabase**. Se a conexão ou o SQL não estiverem prontos, ele informa erro e não salva em SQLite ou localStorage como alternativa. O servidor continua necessário para os cookies de sessão HttpOnly. Para operação externa, falta hospedar esse servidor atrás de HTTPS com `CONTROLAI_SECURE_COOKIE=1`.

A API Auth do projeto real respondeu HTTP 200 à chave pública; chamadas de dados sem login permanecem bloqueadas. O usuário informou executar o SQL e criar a conta. O SQL e as regras também foram validados em PostgreSQL descartável. Login e gravação com uma conta real ainda precisam ser testados no serviço publicado.

## Migrar registros antigos, caso existam

O SQLite anterior permanece preservado em `/workspace/controlai-data/estoque.sqlite3`. Para usar a versão antiga explicitamente, execute com outra porta:

```sh
CONTROLAI_BACKEND=sqlite CONTROLAI_PORT=8082 python3 server.py
```

Exporte o JSON pela conta administradora antiga e restaure-o pela conta administradora no app conectado ao Supabase. Confira quantidades, pedidos, entregas e obras antes de abandonar a instalação antiga. Essa é uma transferência única de dados, não uma obrigação de backup manual recorrente. Contas/senhas e o histórico técnico SQLite não são transferidos pelo JSON; usuários devem usar o Supabase Auth, e o histórico antigo deve continuar preservado com o arquivo SQLite.

## Backup automático

O backup diário externo está preparado, mas **ainda não ativado**. Depois de confirmar que os dados estão no Supabase, siga [BACKUPS.md](../BACKUPS.md) para configurar o GitHub Actions. A chave pública do app não permite executar `pg_dump`. A conexão PostgreSQL com senha vai somente no secret `SUPABASE_DB_URL` do GitHub. Ainda falta validar uma execução real e um ensaio de recuperação.
