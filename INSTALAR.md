# Instalar o ControlAI

Depois de o Render concluir a publicação e mostrar **Live**, abra o endereço HTTPS real do serviço. A versão inclui manifesto, ícones e service worker para instalação como PWA. Os dados são compartilhados via Supabase, cada pessoa usa sua própria conta.

## Computador

No Chrome ou Edge, abra o endereço do app e clique em **Instalar app**, quando o botão aparecer. Também é possível usar o ícone de instalação na barra de endereço.

- Chrome: menu ⋮ → **Transmitir, salvar e compartilhar → Instalar página como app** (o texto pode variar conforme a versão).
- Edge: menu ⋯ → **Aplicativos → Instalar este site como aplicativo**.

O app fica disponível no menu de aplicativos do computador e pode ser fixado na barra de tarefas/dock.

## Android

Abra o endereço pelo Chrome e use **Instalar app**. Alternativamente, menu ⋮ → **Adicionar à tela inicial → Instalar**. O ícone aparece junto aos outros aplicativos.

## iPhone e iPad

Abra o endereço no **Safari**, toque em **Compartilhar → Adicionar à Tela de Início → Adicionar**. Se aparecer a opção **Abrir como App**, mantenha-a ativada.

## Conexão, atualizações e acesso

O aplicativo precisa de internet para carregar os dados atuais e salvar pedidos/entregas. Se o aparelho estiver sem conexão ao abrir, uma tela informa a indisponibilidade; o worker não armazena cópias do estoque nem respostas de autenticação em cache. Não há gravações offline a sincronizar.

O plano gratuito da hospedagem pode ter uma abertura inicial mais lenta após inatividade. Após uma nova publicação, feche e abra o app para carregar a interface atualizada. Cada instalação tem sua própria sessão; sair em um aparelho não deve ser interpretado como sair de todos.

A instalação depende de a versão atual estar publicada com HTTPS. Testes locais validaram os critérios de instalação do Chromium, a tela offline e a ausência de Cache Storage/localStorage. A instalação em aparelhos físicos e no domínio público ainda deve ser confirmada.
