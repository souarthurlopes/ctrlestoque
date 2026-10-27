const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const html=fs.readFileSync(require('path').join(__dirname,'../index.html'),'utf8');
const context={S:{estoque:[],itens:[]}};vm.createContext(context);
vm.runInContext(html.slice(html.indexOf('const modeloEst='),html.indexOf('/* ---------- cálculos')),context);
context.S.estoque=[{codigo:1,cod_fab:'FACTORY-1000',produto:'EVAPORADORA LG 48 GV',saldo:4},{codigo:2,cod_fab:'FACTORY-1001',produto:'EVAPORADORA LG 36GV',saldo:3},{codigo:3,cod_fab:'FACTORY-1002',produto:'UNIDADE LG 07GS',saldo:2}];
vm.runInContext('prep();globalThis.G=Object.values(grupos());globalThis.a=G.filter(g=>correspondeBusca(g,"48gv"));globalThis.b=G.filter(g=>correspondeBusca(g,"36gv"));',context);
assert.equal(vm.runInContext('G.filter(g=>correspondeBusca(g,"07gs")).length',context),1);
assert.equal(context.a.length,1);assert.equal(context.a[0].saldo,4);assert.equal(context.b.length,1);assert.equal(context.b[0].saldo,3);assert.notEqual(context.a[0].chave,context.b[0].chave);
const groups={};for(let i=0;i<401;i++){groups['model'+i]={chave:'model'+i,label:'Model '+String(i).padStart(3,'0'),tipo:'Evaporadora',saldo:i===400?0:1,vars:['Model '+i],busca:[]};}
const elements={'#q':{value:''},'#sv':{checked:true},'#tbEst':{},'#bq':{value:''},'#pp':{}};
context.$=s=>elements[s];context.grupos=()=>groups;context.tipoSel='Evaporadora';context.esc=s=>s;context.tabela=(_,rows)=>{context.rows=rows;return 'table';};
vm.runInContext(html.slice(html.indexOf('function fillEst()'),html.indexOf('const vObras=')),context);
vm.runInContext(html.slice(html.indexOf('function fillProd()'),html.indexOf('const bad=')),context);
vm.runInContext('fillEst();fillProd();',context);
assert.equal(context.rows.length,400);assert.equal((elements['#pp'].innerHTML.match(/<option /g)||[]).length,401);
assert.ok(elements['#tbEst'].innerHTML.includes('saldo zero ou negativo'));
elements['#sv'].checked=false;vm.runInContext('fillEst()',context);assert.equal(context.rows.length,401);
console.log('PASS: busca por 48GV/36GV nas descrições, separação de modelos, listas completas acima de 300/200, filtro de saldo explícito.');
