const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const html=fs.readFileSync(require('path').join(__dirname,'../index.html'),'utf8');const c={tipoEquipamento:()=> 'Outros',TextDecoder};vm.createContext(c);
vm.runInContext(html.slice(html.indexOf('const cabNormal='),html.indexOf('/* ---------- agrupamento')),c);
function extract(rows){c.rows=rows;return vm.runInContext('extrair(rows)',c);}
const header=[' Código ','Descrição','Und','Fabricante','Cód. Fabricante','Classificação','Saldo','Valor total'];
const rows=[header,['AC-1','Equipamento 48GV','UN','LG','MODEL-1','',4,1000],['00002','Equipamento 36GV','UN','LG','MODEL-2','',0,0],[7,'Equipamento 07GS','UN','LG','MODEL-3','','1.000,00',1200],[null,'TOTAL',null,null,null,null,1004,2200]];
const out=extract(rows).lista;assert.equal(out.length,3);assert.equal(out[0].codigo,'AC-1');assert.equal(out[1].codigo,'00002');assert.equal(out[2].codigo,7);assert.equal(out[0].saldo,4);assert.equal(out[1].saldo,0);assert.equal(out[2].saldo,1000);assert.ok(out.every(r=>r.tipo==='Outros'));
assert.throws(()=>extract([header,['AC-1','Unidade','','','','','ERRO',10]]),/saldo inválido/);
assert.throws(()=>extract([header,[null,'Unidade sem código','','','','',1,10]]),/nenhum item foi importado parcialmente/);
assert.throws(()=>extract([['Código','Produto','Valor total'],[1,'Unidade',1000]]),/coluna de saldo/);
assert.equal(extract([['Codigo','Produto','27/10/2026'],[1,'Unidade',2]]).lista[0].saldo,2);
const supra=[['E','Código','Produto','Und','Fabricante','Cód. Fabricante','Classificação','Estoque em: ','Entradas','Saídas','Estoque em: '],
 [null,null,null,null,null,null,null,'26/10/2026',null,null,'27/10/2026'],
 [4,1,'UNID EVAP 07GS','UN','LG','ARNU07GSJE4','AR CONDICIONADO',2,0,0,2],
 [4,2,'UNID EVAP 36GV','UN','LG','CRNU36GV2A4','AR CONDICIONADO',4,1,2,3],
 [4,3,'UNID EVAP 48GV','UN','LG','CRNU48GV2A4','AR CONDICIONADO',1,0,1,0]];
const parsed=extract(supra);assert.equal(parsed.lista.length,3);assert.equal(parsed.ref,'27/10/2026');
assert.deepEqual(Array.from(parsed.lista,r=>r.saldo),[2,3,0]);
(async()=>{
 const reader={read:()=>({SheetNames:['Instruções','Estoque'],Sheets:{'Instruções':[['Resumo']],Estoque:rows}}),utils:{sheet_to_json:s=>s}};c.window={XLSX:reader};c.XLSX=reader;c.file={arrayBuffer:async()=>new Uint8Array([0x50,0x4b]).buffer};
 const selected=await vm.runInContext('linhas(file)',c);assert.equal(selected,rows);
 reader.read=()=>({SheetNames:['A','B'],Sheets:{A:rows,B:rows}});
 await assert.rejects(vm.runInContext('linhas(file)',c),/mais de uma aba/);
 console.log('PASS: todos os itens, códigos alfanuméricos/zeros, não classificados, saldos zero/pt-BR, coluna correta, aba de estoque e recusa de importação parcial/ambígua.');
})().catch(e=>{console.error(e);process.exitCode=1});
