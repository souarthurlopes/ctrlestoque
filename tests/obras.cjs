const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const html=fs.readFileSync(require('path').join(__dirname,'../index.html'),'utf8');
const begin=html.indexOf('function proximoId()');const end=html.indexOf('const save=',begin);
function allocation(state){const ctx={S:state};vm.createContext(ctx);vm.runInContext(html.slice(begin,end),ctx);return()=>vm.runInContext('proximoId()',ctx);}
let state={obras:[{id:1},{id:8}],itens:[{id:12}],nid:1};let next=allocation(state);
assert.equal(next(),13);assert.equal(next(),14);assert.equal(state.nid,15);
assert.equal(state.obras.length,2);assert.equal(state.itens[0].id,12);
assert.equal(allocation({obras:[{id:'9'}],itens:[],nid:null})(),10);
assert.equal(allocation({obras:[],itens:[]})(),1);
assert.equal(allocation({obras:[],itens:[],nid:30})(),30);
assert.equal(allocation({obras:[{id:5}],itens:[],nid:'6'})(),6);
console.log('PASS: nova obra não reutiliza IDs com contador antigo, nulo ou ausente; respeita IDs dos equipamentos e preserva registros.');
