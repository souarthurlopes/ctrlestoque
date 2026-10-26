let usuarioAtual = null;
let provedorConta = 'sqlite';
let csrfSessao = '';
let conviteAtual = new URLSearchParams(location.hash.slice(1)).get('convite');
let painelAcesso = false;
const authRoot = document.querySelector('#auth-root');
async function apiConta(path, data) {
  const response = await fetch(path, data === undefined ? {cache:'no-store'} : {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrfSessao}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw Error(result.error || 'Não foi possível concluir.');
  return result;
}
function mostrarLogin(setup = false) {
  document.body.classList.remove('autenticado');
  usuarioAtual = null;csrfSessao = '';
  authRoot.innerHTML = `<section class="auth-card"><div class="brand"><span class="brandmark">❄</span><span>Control<em>AI</em></span></div><h2>${conviteAtual ? 'Ative seu acesso' : setup ? 'Seu primeiro acesso' : 'Bem-vindo de volta'}</h2><p>${conviteAtual ? 'Defina sua senha pessoal. A conta será vinculada ao e-mail indicado pelo administrador.' : setup ? 'Crie a conta de administrador para começar a organizar seu estoque.' : 'Entre para acessar os equipamentos e pedidos da equipe.'}</p><form id="formLogin">
  ${setup && !conviteAtual ? '<label>Código de ativação<input name="codigo" required autocomplete="off"></label><label>Seu nome<input name="nome" required maxlength="150" autocomplete="name"></label>' : ''}
  ${!conviteAtual ? '<label>E-mail<input type="email" name="email" required maxlength="254" autocomplete="username"></label>' : ''}
  <label>Senha<input name="senha" type="password" required minlength="${setup || conviteAtual ? 12 : 1}" maxlength="128" autocomplete="${setup || conviteAtual ? 'new-password' : 'current-password'}"></label>
  ${setup || conviteAtual ? '<label>Confirmar senha<input name="confirmacao" type="password" required minlength="12" maxlength="128" autocomplete="new-password"></label><p class="mu">Use pelo menos 12 caracteres. Não compartilhe sua senha.</p>' : ''}
  <div class="auth-error" role="alert" id="erroLogin"></div><button class="b" type="submit">${conviteAtual ? 'Ativar minha conta' : setup ? 'Criar administrador' : 'Entrar'}</button></form>
  <small>${setup && !conviteAtual ? 'A ativação exige o código do servidor. No terminal da instalação, execute: <code>python3 server.py setup-code</code>. Informe o código apenas nesta tela.' : 'Acesso restrito à equipe. Para obter acesso, solicite um convite ao administrador.'}</small></section>`;
  document.querySelector('#formLogin').addEventListener('submit', async e => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    const button = e.target.querySelector('button');button.disabled = true;
    document.querySelector('#erroLogin').textContent = '';
    try {
      if ((setup || conviteAtual) && d.senha !== d.confirmacao) throw Error('As senhas não coincidem.');
      const path = conviteAtual ? '/api/auth/accept' : setup ? '/api/auth/setup' : '/api/auth/login';
      const result = await apiConta(path, {...d, token:conviteAtual});
      conviteAtual = null;history.replaceState(null, '', location.pathname);
      await entrarConta(result);
    } catch (error) {
      document.querySelector('#erroLogin').textContent = error.message;
      button.disabled = false;
    }
  });
}
async function entrarConta(result) {
  provedorConta = result.provider || provedorConta;
  usuarioAtual = result.user;csrfSessao = result.csrf;
  armazenamentoBloqueado = false;filaSalvar = Promise.resolve(true);
  document.body.classList.add('autenticado');
  await iniciarServidor();
}
async function iniciarAutenticacao() {
  try {
    const result = await apiConta('/api/auth/status');
    provedorConta = result.provider || 'sqlite';
    if (provedorConta === 'supabase') conviteAtual = null;
    if (result.user && !conviteAtual) await entrarConta(result);
    else mostrarLogin(result.setupRequired);
  } catch (error) {
    authRoot.innerHTML = '<section class="auth-card"><h2>Servidor indisponível</h2><p>Inicie o servidor Python e recarregue a página.</p></section>';
  }
}
const renderSemConta = render;
render = function () {
  if (!usuarioAtual) return;
  if (aba === 'bkp' && usuarioAtual.papel !== 'admin') aba = 'est';
  painelAcesso = false;
  renderSemConta();
  document.querySelector('[data-a="bkp"]').hidden = usuarioAtual.papel !== 'admin';
  // hidden prevalece sobre o display:flex definido no menu.
  document.querySelector('[data-a="bkp"]').style.display = usuarioAtual.papel === 'admin' ? '' : 'none';
  document.querySelector('main').insertAdjacentHTML('afterbegin', `<div class="accountbar"><span class="identity">${esc(usuarioAtual.nome)} · ${usuarioAtual.papel === 'admin' ? 'Administrador · acesso completo' : 'Acesso operacional'}</span>${usuarioAtual.papel === 'admin' ? '<button class="b g" id="gerirAcessos">Usuários e histórico</button>' : ''}<button class="b g" id="sairConta">Sair</button></div>`);
  document.querySelector('.profile').textContent = usuarioAtual.nome;
  document.querySelector('#gerirAcessos')?.addEventListener('click', mostrarAcessos);
  document.querySelector('#sairConta').addEventListener('click', async () => {
    try {await filaSalvar;await apiConta('/api/auth/logout', {});location.reload();}
    catch(error){if(error.message.includes('Entre na sua conta'))location.reload();else alert(error.message);}
  });
};
async function mostrarAcessos() {
  if (usuarioAtual?.papel !== 'admin') return;
  try {
    const [data, audit] = await Promise.all([apiConta('/api/users'),apiConta('/api/audit')]);
    document.querySelector('#painelAcessos')?.remove();
    const html = `<section class="cd access-panel" id="painelAcessos"><h2>Equipe e acessos</h2><p>${provedorConta === 'supabase' ? 'Você tem acesso completo. Autorize até dois usuários de apoio com as mesmas permissões operacionais. As contas de login são criadas no painel Supabase; esta tela controla quem pode acessar o ControlAI.' : 'Até três acessos ativos: você e dois usuários de apoio com as mesmas permissões operacionais. Cada convite vale por 48 horas e pode ser usado uma vez.'}</p>
    ${tabela(['Pessoa','E-mail','Permissão','Acesso',''],data.users.map(u=>[esc(u.nome),esc(u.email),u.papel==='admin'?'Administrador':'Operacional',u.ativo?(u.pendente?'Aguardando primeiro login':'Ativo'):'Desativado',u.papel==='admin'?'Você tem acesso completo':`<button class="b g" data-acesso="${esc(u.id)}" data-ativo="${!u.ativo}">${u.ativo?'Desativar':'Reativar'}</button>`]))}
    <form id="convidarPessoa"><div class="row"><label>Nome<input name="nome" required maxlength="150"></label><label>E-mail<input name="email" type="email" required maxlength="254"></label><button class="b" type="submit">${provedorConta === 'supabase' ? 'Autorizar acesso' : 'Gerar convite'}</button></div></form><div id="resultadoConvite" aria-live="polite"></div>
    ${data.invitations.length?'<h3>Convites pendentes</h3>'+tabela(['Pessoa','E-mail','Validade',''],data.invitations.map(i=>[esc(i.nome),esc(i.email),esc(new Date(i.expira*1000).toLocaleString('pt-BR')),`<button class="b g" data-revogar="${esc(i.email)}">Revogar</button>`])):''}
    <h3>Últimos registros do sistema</h3><p>Horários registrados pelo servidor. O histórico continua preservado após restaurar um backup de dados.</p>${tabela(['Data','Usuário','Ação','Detalhes'],audit.registros.map(r=>[esc(new Date(r.em*1000).toLocaleString('pt-BR')),esc(r.usuario),esc(({login:'Entrou',logout:'Saiu',conta_ativada:'Conta ativada',dados_atualizados:'Dados salvos',backup_restaurado:'Backup restaurado',convite_criado:'Convite criado',convite_revogado:'Convite revogado',acesso_alterado:'Acesso alterado'})[r.acao]||r.acao),esc(r.detalhes.alteracoes?r.detalhes.alteracoes.map(a=>`${a.tipo}: ${a.acao}${a.id?' #'+a.id:''}`).join('; '):r.detalhes.email||r.detalhes.papel||'')]))}</section>`;
    document.querySelector('.accountbar').insertAdjacentHTML('afterend', html);
    const panel = document.querySelector('#painelAcessos');
    panel.querySelector('#convidarPessoa').addEventListener('submit', async e => {
      e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;
      const output=panel.querySelector('#resultadoConvite');
      try {
        const result=await apiConta('/api/invitations',Object.fromEntries(new FormData(e.target)));
        if (result.mode === 'supabase') {
          output.className='invite-output';output.textContent=result.message;e.target.reset();return;
        }
        const link=location.origin+location.pathname+'#convite='+encodeURIComponent(result.token);
        output.className='invite-output';output.replaceChildren();
        const text=document.createElement('p');text.textContent='Convite gerado. Copie o link e envie diretamente à pessoa convidada. Quem receber o link poderá ativar essa conta. O link não será exibido novamente.';
        const input=document.createElement('input');input.readOnly=true;input.value=link;input.setAttribute('aria-label','Link de convite');input.addEventListener('click',()=>input.select());
        output.append(text,input);e.target.reset();
      }catch(error){output.textContent=error.message;}finally{button.disabled=false;}
    });
    panel.querySelectorAll('[data-acesso]').forEach(button=>button.addEventListener('click',async()=>{
      if(!confirm('Confirmar alteração do acesso desta pessoa?'))return;
      try{await apiConta('/api/users/active',{id:provedorConta === 'supabase' ? button.dataset.acesso : Number(button.dataset.acesso),ativo:button.dataset.ativo==='true'});await mostrarAcessos();}catch(error){alert(error.message);}
    }));
    panel.querySelectorAll('[data-revogar]').forEach(button=>button.addEventListener('click',async()=>{
      try{await apiConta('/api/invitations/revoke',{email:button.dataset.revogar});await mostrarAcessos();}catch(error){alert(error.message);}
    }));
    panel.scrollIntoView({behavior:'smooth',block:'start'});
  }catch(error){alert(error.message);}
}
async function baixarBackupServidor() {
  try {await filaSalvar;const data=await apiConta('/api/backup');await baixar('backup-controlai.json',JSON.stringify(data.state));}
  catch(error){flash(error.message);}
}
async function restaurarBackupServidor(state) {
  try {
    await filaSalvar;
    const result=await apiConta('/api/restore',{revision:revisaoServidor,state});
    S=result.state;revisaoServidor=result.revision;prep();return true;
  }catch(error){flash(error.message);return false;}
}
