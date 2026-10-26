/* Pedidos preservam os dados do atendimento. O saldo continua sendo do Supra. */
const pedidos = () => S.pedidos || [];
const gruposClimatizacao = () => Object.fromEntries(Object.entries(grupos()).filter(([, g]) => ['Evaporadora', 'Condensadora'].includes(g.tipo)));
const entregas = () => S.entregas || [];
const entregue = (pedido, linha) => entregas().filter(e => e.pedidoId === pedido && e.linhaId === linha).reduce((n, e) => n + e.qtd, 0);
const dataPedido = value => new Date(value).toLocaleString('pt-BR');
async function gravarPedido(alterar) {
  const anterior = JSON.stringify(S);
  try {
    alterar();
    return await salvarServidor();
  } catch (e) {
    S = JSON.parse(anterior);
    flash('Não foi possível salvar. Nenhuma alteração foi aplicada. Confira a conexão com o servidor.');
    return false;
  }
}
function vPedidos() {
  const G = gruposClimatizacao();
  const status = p => {
    const total = p.linhas.reduce((n, l) => n + l.qtd, 0);
    const feito = p.linhas.reduce((n, l) => n + entregue(p.id, l.id), 0);
    return feito === total ? 'Atendido' : feito ? 'Parcialmente atendido' : 'Pendente';
  };
  return `<div class="msg">O saldo oficial vem do Supra. Registre a saída no Supra no momento da entrega. Os atendimentos abaixo preservam o histórico e não descontam novamente o saldo importado. Consulte o Supra para confirmar a disponibilidade antes da entrega.</div>
  <div class="cd"><h2>Novo pedido</h2>${!S.obras.length || !Object.keys(G).length ? '<p class="mu">Cadastre uma obra e importe o estoque para criar pedidos.</p>' : `
  <form id="novoPedido"><div class="row">
  <label>Obra / destino<select name="obra" required>${S.obras.map(o => `<option value="${o.id}">${esc(o.nome)}</option>`).join('')}</select></label>
  <label>Solicitante<input name="solicitante" required maxlength="150"></label>
  <label>Equipamento<select name="modelo" required>${Object.values(G).map(g => `<option value="${esc(g.chave)}">${esc(g.label)}</option>`).join('')}</select></label>
  <label>Quantidade<input name="qtd" type="number" min="1" step="1" required style="width:100px"></label>
  <label>Ambiente / pavimento<input name="ambiente" maxlength="150"></label>
  <button class="b" type="submit">Criar pedido</button></div><p class="mu">Após criar, você pode incluir outros equipamentos no mesmo pedido.</p></form>`}</div>
  ${pedidos().slice().reverse().map(p => `<section class="cd"><h2>${esc(p.numero)} · ${esc(p.obraNome)} <span class="${status(p) === 'Atendido' ? 'ok' : 'mu'}">· ${status(p)}</span></h2>
  <p class="mu">Solicitado por ${esc(p.solicitante)} · ${esc(dataPedido(p.criadoEm))}${p.criadoPor ? ` · Registrado por ${esc(p.criadoPor.nome)}` : ''}<br>Destino: ${esc(p.endereco || p.obraNome)}</p>
  ${tabela(['Equipamento', 'Ambiente', 'Solicitado', 'Entregue', 'Pendente'], p.linhas.map(l => [esc(l.modelo), esc(l.ambiente), l.qtd, entregue(p.id, l.id), l.qtd - entregue(p.id, l.id)]))}
  <details style="margin-top:16px"><summary>Adicionar equipamento ao pedido</summary><form class="incluirLinha" data-pedido="${p.id}"><div class="row" style="margin-top:12px"><label>Equipamento<select name="modelo" required>${Object.values(G).map(g => `<option value="${esc(g.chave)}">${esc(g.label)}</option>`).join('')}</select></label><label>Quantidade<input name="qtd" type="number" min="1" step="1" required></label><label>Ambiente / pavimento<input name="ambiente" maxlength="150"></label><button class="b" type="submit">Incluir equipamento</button></div></form></details>
  ${p.linhas.some(l => l.qtd > entregue(p.id, l.id)) ? `<details style="margin-top:16px"><summary>Registrar entrega</summary><form class="registrarEntrega" data-pedido="${p.id}"><div class="row" style="margin-top:12px"><label>Equipamento<select name="linha" required>${p.linhas.filter(l => l.qtd > entregue(p.id, l.id)).map(l => `<option value="${l.id}">${esc(l.modelo)} · ${esc(l.ambiente || 'Sem ambiente')} · pendente ${l.qtd - entregue(p.id, l.id)}</option>`).join('')}</select></label><label>Quantidade entregue<input name="qtd" type="number" min="1" step="1" required></label><label>Entregue por<input name="responsavel" required maxlength="150"></label><label>Recebido por<input name="recebedor" required maxlength="150"></label><label>Referência da saída no Supra<input name="referencia" required maxlength="150" placeholder="Documento / lançamento"></label><button class="b" type="submit">Confirmar entrega</button></div><p class="mu">Confirme somente após registrar a saída no Supra. O horário atual será registrado.</p></form></details>` : ''}
  <details style="margin-top:16px"><summary>Histórico de atendimento (${entregas().filter(e => e.pedidoId === p.id).length})</summary>${tabela(['Data', 'Equipamento', 'Qtd', 'Entregue por', 'Recebido por', 'Saída Supra', 'Registrado por'], entregas().filter(e => e.pedidoId === p.id).map(e => [esc(dataPedido(e.em)), esc(e.modelo), e.qtd, esc(e.responsavel), esc(e.recebedor), esc(e.referencia), esc(e.criadoPor?.nome || 'Registro anterior ao login')]))}</details></section>`).join('') || '<div class="cd"><h2>Seus pedidos aparecerão aqui</h2><p class="mu">Registre a primeira solicitação para acompanhar as entregas por obra.</p></div>'}`;
}
document.addEventListener('submit', async e => {
  const f = e.target;
  if (!(f.matches('#novoPedido, .incluirLinha, .registrarEntrega'))) return;
  e.preventDefault();
  if (!f.reportValidity()) return;
  const d = Object.fromEntries(new FormData(f));
  const qtd = Number(d.qtd);
  if (!Number.isSafeInteger(qtd) || qtd < 1) return flash('Informe uma quantidade inteira maior que zero.');
  const G = gruposClimatizacao();
  const p = pedidos().find(p => p.id === f.dataset.pedido);
  if (f.matches('#novoPedido, .incluirLinha')) {
    const g = G[d.modelo];
    if (!g) return flash('O modelo não está mais no estoque importado.');
    const linha = { id: crypto.randomUUID(), chave: g.chave, modelo: g.label, qtd, ambiente: d.ambiente.trim(), criadoEm: new Date().toISOString() };
    if (f.id === 'novoPedido') {
      const obra = S.obras.find(o => o.id === Number(d.obra));
      if (!obra || !d.solicitante.trim()) return flash('Informe a obra e o solicitante.');
      if (await gravarPedido(() => {
        S.pedidos ||= [];
        const numero = Math.max(0, ...S.pedidos.map(p => Number(p.sequencia) || 0)) + 1;
        S.pedidos.push({ id: crypto.randomUUID(), sequencia: numero, numero: 'PED-' + String(numero).padStart(4, '0'), obraId: obra.id, obraNome: obra.nome, endereco: obra.end, solicitante: d.solicitante.trim(), criadoEm: new Date().toISOString(), linhas: [linha] });
      })) flash('Pedido criado.');
    } else {
      if (!p) return flash('Pedido não encontrado.');
      if (await gravarPedido(() => p.linhas.push(linha))) flash('Equipamento incluído no pedido.');
    }
  } else {
    const l = p?.linhas.find(l => l.id === d.linha);
    if (!l) return flash('Item do pedido não encontrado.');
    if (qtd > l.qtd - entregue(p.id, l.id)) return flash('A quantidade excede o saldo pendente do pedido.');
    if (![d.responsavel, d.recebedor, d.referencia].every(v => v?.trim())) return flash('Preencha os responsáveis e a referência da saída no Supra.');
    if (await gravarPedido(() => {
      S.entregas ||= [];
      S.entregas.push({ id: crypto.randomUUID(), pedidoId: p.id, linhaId: l.id, modelo: l.modelo, chave: l.chave, obraNome: p.obraNome, ambiente: l.ambiente, qtd, responsavel: d.responsavel.trim(), recebedor: d.recebedor.trim(), referencia: d.referencia.trim(), em: new Date().toISOString() });
    })) flash('Entrega registrada. O saldo importado do Supra foi preservado.');
  }
});
