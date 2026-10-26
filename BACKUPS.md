# Backups automáticos do Supabase gratuito

Projeto informado: `https://uyeopkssqzxjaooqjehl.supabase.co`.

## Estado real

A rotina está preparada no código, **ainda não ativada**. O app foi adaptado para Supabase, mas o SQL, as contas e a migração dos dados reais ainda precisam ser aplicados. Esta rotina copia apenas o que estiver no banco Supabase; não protege o arquivo SQLite legado. Consulte [supabase/LEIA-ME.md](supabase/LEIA-ME.md) para concluir a conexão antes de ativar os backups.

O agendamento roda no GitHub Actions, diariamente por volta de 03h15 em São Paulo. O GitHub pode atrasar ou interromper execuções conforme disponibilidade, inatividade do repositório e limites do plano. Cada arquivo é criptografado antes de sair do executor e retido como artefato por 14 dias, fora do Supabase. O download manual não é necessário para criar essas cópias. Há limites de armazenamento e minutos do GitHub; acompanhe Usage/Billing antes de habilitar para não assumir gratuidade ilimitada.

## Configuração segura

1. Envie os arquivos do projeto ao repositório `souarthurlopes/ctrlestoque`, na branch padrão. Isso ainda não foi feito por este trabalho. Agendamentos do Actions usam a branch padrão.
2. Obtenha a conexão PostgreSQL no botão **Connect** do Supabase. Prefira **Session pooler** na porta 5432 quando o executor não tiver IPv6. Não use a URL `/rest/v1/` nem transaction pooler na porta 6543. A senha faz parte da conexão; caracteres especiais precisam ser codificados na URL.
3. No repositório GitHub, abra **Settings → Secrets and variables → Actions**. Cadastre `SUPABASE_DB_URL` como **secret**, nunca no código ou chat.
4. Gere uma chave OpenPGP dedicada em um dispositivo sob seu controle, por exemplo com `gpg --full-generate-key`, incluindo capacidade de criptografia. Guarde a chave privada e sua senha de recuperação em local seguro, separado do projeto. Sem essa chave, o backup é irrecuperável. Não envie a chave privada para o Actions.
5. Em **Variables**, adicione `BACKUP_PUBLIC_KEY` com a chave pública ASCII e `BACKUP_KEY_FINGERPRINT` com sua impressão digital completa. Se o certificado do banco não for confiável pela cadeia padrão, adicione o certificado CA obtido no painel Supabase à variável pública `SUPABASE_DB_CA_CERT`. A conexão exige TLS verificado (`verify-full`); não desative a verificação para contornar falhas.
6. Defina `SUPABASE_BACKUP_ENABLED` como `true`. Rode o workflow manualmente em **Actions** para validar a primeira cópia. Verifique que o job terminou com sucesso e que criou o artefato criptografado. Um job ignorado não é um backup.
7. Confira as notificações de falhas do GitHub Actions. Faça um ensaio de restauração em um banco separado antes de considerar a recuperação comprovada.

A rotina não é ativada apenas por salvar arquivos localmente. Não foram configurados secrets, criado agendamento remoto ou gerado backup real. Não há envio de e-mails por este código.

## Conteúdo e recuperação

O `pg_dump` cria um arquivo de formato customizado com estrutura e dados do banco acessíveis à conta utilizada, sem proprietários nem permissões. Não inclui arquivos binários do Supabase Storage, configurações de autenticação/provedores, secrets de Edge Functions ou configurações do projeto. Falha de permissão em qualquer parte do dump faz o job falhar; não publica uma cópia parcial como concluída. A listagem com `pg_restore --list` verifica o formato, mas não prova restauração completa.

Para recuperar, baixe o artefato, confira o SHA-256, use a chave privada no seu dispositivo para descriptografar e ensaie o `pg_restore` em um banco isolado. Projetos Supabase têm schemas e objetos gerenciados; a restauração precisa ser planejada para não sobrescrever esses objetos sem análise. Nunca teste a recuperação diretamente no banco de produção. O backup não oferece recuperação contínua ponto a ponto.

O script requer Python 3, GnuPG, `pg_dump` e `pg_restore` compatíveis com a versão do servidor. O workflow usa os clientes PostgreSQL 18. No ambiente local não foram encontrados os clientes PostgreSQL; o backup real depende dessa configuração e das credenciais seguras.
