let revisaoServidor = 0;
let filaSalvar = Promise.resolve(true);
let armazenamentoBloqueado = false;
let gravacoesPendentes = 0;
function bloquearArmazenamento(mensagem) {
  armazenamentoBloqueado = true;
  document.querySelector('main').replaceChildren();
  const box = document.createElement('div');
  box.className = 'msg';
  box.textContent = mensagem + ' Recarregue para obter os dados salvos. Se havia dados em outro navegador, use o backup JSON do app anterior para migrar.';
  document.querySelector('main').append(box);
}
function salvarServidor() {
  const estado = JSON.parse(JSON.stringify(S));
  gravacoesPendentes++;
  filaSalvar = filaSalvar.then(async () => {
    if (armazenamentoBloqueado) return false;
    try {
      const response = await fetch('/api/state', {method:'PUT', headers:{'Content-Type':'application/json','X-CSRF-Token':csrfSessao}, body:JSON.stringify({revision:revisaoServidor,state:estado})});
      const result = await response.json();
      if (!response.ok) throw Error(result.error || 'Erro ao salvar');
      revisaoServidor = result.revision;
      if (JSON.stringify(S) === JSON.stringify(estado)) S = result.state;
      return true;
    } catch (error) {
      bloquearArmazenamento('A alteração não foi confirmada no servidor. ' + error.message);
      return false;
    }
  }).finally(() => { gravacoesPendentes--; });
  return filaSalvar;
}
async function iniciarServidor() {
  try {
    const response = await fetch('/api/state', {cache:'no-store'});
    if (!response.ok) throw Error('Servidor indisponível');
    const data = await response.json();
    S = Object.assign(S, data.state);
    revisaoServidor = data.revision;
    prep();render();
  } catch (error) {
    bloquearArmazenamento('Não foi possível carregar o banco de dados. Inicie o app pelo servidor Python.');
  }
}
// Impede continuar editando dados que não foram confirmados.
document.addEventListener('click', e => {if(armazenamentoBloqueado && !e.target.closest('#sairConta')){e.preventDefault();e.stopImmediatePropagation();}},true);
document.addEventListener('submit', e => {if(armazenamentoBloqueado && !e.target.closest('#sairConta')){e.preventDefault();e.stopImmediatePropagation();}},true);

window.addEventListener('beforeunload', e => { if (gravacoesPendentes > 0) { e.preventDefault(); e.returnValue = ''; } });
