const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const html=fs.readFileSync(require('path').join(__dirname,'../index.html'),'utf8');
const context={S:{estoque:[],itens:[],pedidos:[],entregas:[]}};vm.createContext(context);
const begin=html.indexOf('const modeloEst=');const end=html.indexOf('/* ---------- cálculos',begin);
vm.runInContext(html.slice(begin,end),context);
const input=[
{codigo:1,cod_fab:'ARUN100LSS0',produto:'Unidade externa VRF 10HP',tipo:'Outros',chave:'ARUN100LSS0',saldo:2},
{codigo:2,cod_fab:'crun100lss0',produto:'VRF 10HP',tipo:'Outros',chave:'CRUN100LSS0',saldo:3},
{codigo:3,cod_fab:'ARUN120LSS0',produto:'VRF 12HP',tipo:'Outros',saldo:4},
{codigo:4,cod_fab:'ARNU09GM1A4',produto:'Unidade interna',tipo:'Outros',saldo:5},
{codigo:5,cod_fab:'CRNU09GM1A4',produto:'Unidade interna',tipo:'Outros',saldo:6},
{codigo:6,cod_fab:'',produto:'LG CRUN140LSS0 VRF',tipo:'Outros',chave:'cod:6',saldo:1},
{codigo:7,cod_fab:'BRUN100LSS0',produto:'Outro equipamento',tipo:'Outros',saldo:8}
];
context.S.estoque=input;
context.S.itens=[{id:1,chave:'RUN100LSS0'},{id:2,chave:'ARUN100LSS0'},{id:3,chave:'CRUN100LSS0'},{id:4,chave:'cod:6'},{id:5,codigo:3}];
context.S.pedidos=[{id:'p1',linhas:[{id:'l1',chave:'CRUN100LSS0'}]}];context.S.entregas=[{id:'e1',chave:'CRUN100LSS0'}];const before=JSON.stringify([context.S.pedidos,context.S.entregas]);
vm.runInContext('prep();globalThis.G=grupos();globalThis.labels=S.itens.map(i=>lab(i.chave,G));',context);
assert.equal(Object.keys(context.G).length,5);
assert.equal(context.G.RUN100LSS0.saldo,5);assert.equal(context.G.RUN100LSS0.tipo,'Condensadora');
assert.equal(context.G.RUN100LSS0.label,'ARUN100LSS0 / CRUN100LSS0');
assert.equal(context.G.RUN120LSS0.saldo,4);assert.equal(context.G.RNU09GM1A4.saldo,11);assert.equal(context.G.RNU09GM1A4.tipo,'Evaporadora');
assert.equal(context.G.RUN140LSS0.saldo,1);assert.equal(context.G.BRUN100LSS0.tipo,'Outros');
assert.ok(context.labels.every(l=>!l.includes('fora do Supra')));
assert.equal(context.S.itens[0].chave,'RUN100LSS0');assert.equal(context.S.itens[1].chave,'RUN100LSS0');assert.equal(context.S.itens[2].chave,'RUN100LSS0');
assert.equal(JSON.stringify([context.S.pedidos,context.S.entregas]),before);
const repeat=JSON.stringify(context.S);vm.runInContext('prep()',context);assert.equal(JSON.stringify(context.S),repeat);
// Importações novas classificam pelo modelo mesmo sem a palavra COND.
vm.runInContext(html.slice(html.indexOf('function extrair('),html.indexOf('/* ---------- agrupamento')),context);
vm.runInContext('globalThis.achaCab=rows=>rows.findIndex(r=>r&&r.includes("Código"))',context);
context.rows=[['Código','Produto','Und','Fabricante','Cód. Fabricante','Classificação','Saldo'],[10,'Unidade VRF','UN','LG','CRUN200LSS0','VRF',2]];
vm.runInContext('globalThis.importado=extrair(rows)',context);assert.equal(context.importado.lista[0].tipo,'Condensadora');
console.log('PASS: ARUN/CRUN e ARNU/CRNU, saldos, modelos distintos, importação/classificação, referências antigas, repetibilidade e histórico preservado.');
