# Migrar do Render para Cloudflare Workers

A versão Workers mantém o mesmo Supabase e as mesmas contas. Não é necessário copiar o banco ou executar novamente o SQL para trocar a hospedagem. A migração ainda depende de publicar na conta Cloudflare e testar o endereço real.

## Publicar pela sua conta

1. No Cloudflare, abra **Workers & Pages → Create application → Import a repository** (ou **Connect GitHub**, conforme o painel).
2. Autorize e selecione `souarthurlopes/ctrlestoque`, branch `main`.
3. Nome do Worker: **estoqai**, igual ao `name` em `wrangler.jsonc`. Deixe o diretório raiz na raiz do repositório.
4. Instalação: `npm ci`. Se houver campo de build, use `npm run build`.
5. Comando de publicação: `npx wrangler deploy`. O `wrangler.jsonc` também executa o build, de forma repetível, antes de publicar.
6. Publique e abra o endereço HTTPS atribuído ao Worker. O endereço definitivo aparece no painel; não foi criado por preparar os arquivos localmente.

O ambiente de build precisa de Node 22 ou superior, indicado em `package.json`. Não use os comandos Python/Gunicorn do Render neste projeto Workers. Os arquivos estáticos são enviados por Workers Assets, e as rotas `/api/` executam no Worker.

A configuração pública do Supabase já está no projeto. Não coloque senha de banco, service_role ou token de usuário em variáveis do frontend. O GitHub conectado ao Cloudflare cuida da autorização de publicação; não é preciso enviar token pelo chat. Os testes do ambiente confirmaram que não havia uma sessão Wrangler autenticada, portanto nenhuma publicação remota foi feita por este trabalho.

## Conferir e concluir a troca

1. No novo endereço, entre com a conta Supabase já existente.
2. Confira o estoque e pesquise modelos por partes do nome.
3. Em **Obras → Editar**, altere um cadastro de teste, salve e confira ao recarregar.
4. Valide criação de pedido e leitura das entregas existentes, sem gerar entregas fictícias em produção.
5. Depois de validar o novo endereço, desative o auto-deploy e remova o Web Service antigo no Render pelo painel. O banco não é apagado: permanece no Supabase.
6. Os atalhos/PWAs instalados com o endereço Render continuam apontando para ele. Instale o app a partir do novo endereço Cloudflare e substitua os atalhos antigos.

A edição de uma obra mantém o identificador, os itens e o histórico de pedidos/entregas. Os nomes/endereço guardados em atendimentos antigos continuam como registrados naquela ocasião. Cancelar a edição não grava; nomes duplicados são recusados; só há confirmação após resposta do servidor.

## Desenvolvimento e validação

```sh
npm ci
npm test
npm run check:worker
npm run dev
```

`check:worker` é um dry-run: valida e empacota sem publicar. `dev` executa o runtime local do Workers. O build copia uma lista explícita de 11 arquivos públicos para `dist/public`; código Python, SQL, configurações privadas, bancos e testes não são servidos. `node_modules`, `dist`, `.wrangler` e `.dev.vars` ficam ignorados pelo Git.

Neste ambiente gerenciado, use `WRANGLER_LOG_PATH=/tmp/controlai-wrangler.log WRANGLER_SEND_METRICS=false` antes dos comandos Wrangler para manter logs em local gravável. Preserve o proxy e a verificação TLS. Os arquivos e testes preparados não são publicação na conta Cloudflare.

## Dados, acesso e limites

O Worker usa a chave publishable e o JWT de cada usuário. O Supabase continua verificando RLS, autorização, papel, revisões de gravação e preservação do histórico. Tokens ficam em cookies HttpOnly/SameSite, com Secure nas requisições HTTPS. As operações de escrita verificam origem e CSRF. Não há armazenamento do estoque no navegador nem em um banco alternativo do Cloudflare. O Health Check `/healthz` confirma o processo, não o banco.

Workers Free tem limites de uso e o painel informa a disponibilidade na sua conta. A migração de hospedagem não ativa backups: o agendamento criptografado no GitHub continua uma etapa separada em `BACKUPS.md`, ainda pendente de configuração e validação real.

A versão Python do Render foi preservada como opção de retorno durante a troca. Sua remoção do código não é necessária para desligar o serviço no painel depois da validação.
