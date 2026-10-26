# ControlAI

Gestão de evaporadoras e condensadoras por obra: estoque importado do Supra, agrupamento ARNU/CRNU, pedidos, entregas parciais e histórico com responsáveis. O Supra continua sendo a fonte oficial do saldo.

## Configurar e executar

O backend padrão é **Supabase**. Siga [supabase/LEIA-ME.md](supabase/LEIA-ME.md) para executar o SQL no seu projeto e criar o primeiro administrador no Supabase Auth. O usuário informou executar o SQL e criar a conta. A conectividade com a API Auth foi confirmada; login e gravação reais ainda precisam ser validados.

```sh
cd /workspace/ctrlestoque
python3 server.py
```

Requer Python 3 padrão, sem instalar pacotes. Servidor local na porta 8081; precisa ser hospedado atrás de HTTPS para uso pela equipe. Não use servidor estático nem abra o HTML diretamente. `CONTROLAI_PORT` configura a porta. `SUPABASE_URL` e `SUPABASE_PUBLISHABLE_KEY` podem sobrescrever a configuração pública em `supabase/config.json`; nunca use service_role. `CONTROLAI_SECURE_COOKIE=1` é necessário quando o app estiver atrás de HTTPS.

## Dados e autenticação

No modo Supabase, dados e histórico ficam no PostgreSQL remoto, usuários e senhas ficam no Supabase Auth, e os tokens usam cookies HttpOnly/SameSite, sem localStorage. O servidor usa apenas chave pública e token do usuário, com TLS verificado. Não há fallback para dados locais quando o Supabase falha.

As tabelas têm RLS ativo e não permitem acesso direto a anon/authenticated. As funções verificam a conta confirmada, a autorização, o papel e os limites de quantidade e preservação do histórico. O administrador também opera o sistema; somente ele gerencia as autorizações, consulta o histórico técnico e restaura/exporta backups. Até dois operadores têm as mesmas permissões operacionais. Nenhum e-mail é enviado automaticamente.

O arquivo SQLite anterior está preservado. Acesso legado só com `CONTROLAI_BACKEND=sqlite`; instruções de migração no guia. Não copie/apague o banco antigo. Tokens e senhas SQLite não são migrados para o Supabase. Dados pré-login não têm autoria comprovada.

## Backups

A rotina diária de backup externo criptografado está preparada, **ainda não ativada**. A chave pública do app não substitui a conexão de backup. Veja [BACKUPS.md](BACKUPS.md). Não considere os dados protegidos por backup automático antes de validar execução e recuperação. Dump não inclui arquivos do Storage nem configurações externas.

## Testes

```sh
python3 -m unittest discover -s tests -v
RUN_POSTGRES_TESTS=1 python3 -m unittest discover -s tests -v
```

A segunda opção usa Docker com a imagem oficial `postgres:18-alpine` já disponível e cria um banco descartável sem rede externa. Os testes não acessam o seu projeto Supabase. Exercitam autenticação legada, ponte HTTPS com respostas simuladas, cookies/CSRF, permissões reais no PostgreSQL, limite de três acessos, conflitos, autoria e preservação de entregas. A criptografia de backup é testada com chave e dados sintéticos; `pg_dump` e restauração de banco real ainda não foram executados.

## Limites restantes

Falta executar o SQL e validar o projeto real, configurar contas, hospedar com HTTPS, ativar o backup externo e testar recuperação. Recuperação/troca de senha por e-mail, conciliação automática de importações e estornos ainda não estão implementados. A importação Excel depende de `cdnjs.cloudflare.com`. Publicar o ambiente de desenvolvimento não equivale a hospedar o app em produção.

## Endereço de acesso

Configuração de publicação com Gunicorn em `render.yaml`; siga [PUBLICAR.md](PUBLICAR.md). O endereço HTTPS será gerado pela hospedagem após a implantação. A preparação local não publicou o serviço.

## Instalar como aplicativo

A interface é uma PWA instalável no computador, Android e iPhone. Instruções em [INSTALAR.md](INSTALAR.md). Necessita da versão atual publicada com HTTPS. O service worker não armazena dados privados nem oferece gravação offline; as informações continuam no Supabase.
