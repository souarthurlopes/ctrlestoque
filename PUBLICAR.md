# Publicar o ControlAI e obter um endereço

O projeto está preparado para um Web Service Python no Render. Ainda não foi publicado: o endereço só existe depois que o serviço termina a implantação. Não é preciso senha de banco nem service_role para hospedar o app; a conexão usa a configuração pública do projeto e o login de cada usuário.

## 1. Colocar o projeto no GitHub

Use o repositório `souarthurlopes/ctrlestoque`, com os arquivos do app na branch `main`. Confirme que `requirements.txt`, `wsgi.py`, `render.yaml`, `index.html` e a pasta `supabase` aparecem diretamente na raiz. Se usar o pacote ZIP como alternativa, extraia os arquivos antes de enviá-los ao GitHub; não envie o ZIP sozinho.

O pacote não contém o banco SQLite, senhas, tokens de sessão, chaves privadas ou arquivos de backup. A chave publishable em `supabase/config.json` é pública. O workflow de backups está incluído, mas permanece desativado até configurar as credenciais de backup e a variável SUPABASE_BACKUP_ENABLED. Publicar o app não o ativa automaticamente.

## 2. Criar o serviço no Render

1. Crie/acesse sua conta em **https://dashboard.render.com/** e conecte o GitHub quando solicitado.
2. Escolha **New → Web Service** e selecione `souarthurlopes/ctrlestoque`.
3. Ambiente **Python**, branch padrão que contém os arquivos, sem Root Directory.
4. **Build Command:** `pip install -r requirements.txt`
5. **Start Command:** `gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60 wsgi:app`
6. Adicione a variável `CONTROLAI_SECURE_COOKIE` com valor `1` e configure o Health Check como `/healthz`.
7. Se disponível na sua conta, escolha o plano **Free** e clique em **Deploy Web Service**. Confira as condições e limites atuais do Render antes de contratar algum plano.

Alternativa: **New → Blueprint**, selecione o repositório e use o `render.yaml`, que já contém esses comandos e variáveis.

Depois de ficar **Live**, o Render mostra o endereço HTTPS real do serviço. Não presuma que `controlai.onrender.com` está disponível: o Render define o subdomínio. O plano gratuito pode suspender o serviço por inatividade, deixando a primeira abertura mais lenta; os dados permanecem no Supabase. Hospedar a interface não ativa o backup externo.

## 3. Testar o serviço publicado

Abra o endereço fornecido pelo Render e entre com a conta que você criou no Supabase. Confira que consegue criar uma obra e lê-la após sair e entrar novamente. Depois teste os acessos de apoio. O SQL e a conta foram informados como criados pelo usuário, mas o login/gravação no projeto real ainda não foram validados neste ambiente.

O endpoint `/healthz` confirma apenas o servidor de aplicação; não comprova a disponibilidade nem o backup do banco remoto. A ponte não salva em SQLite quando o Supabase falha.

## Recuperação e backups

Siga `BACKUPS.md` para configurar os secrets e a chave de criptografia antes de ativar o workflow de backup separado. Ainda falta uma execução real e um ensaio de recuperação. Nenhuma hospedagem ou backup remoto foi ativado por gerar o pacote localmente.
