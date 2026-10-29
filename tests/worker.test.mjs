import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorker} from '../worker/index.mjs';
import {readFile,readdir} from 'node:fs/promises';

const origin='https://estoqai.example.workers.dev';
function setup(options={}) {
  const calls=[];
  const env={SUPABASE_URL:'https://testproject.supabase.co',SUPABASE_PUBLISHABLE_KEY:'sb_publishable_test',ASSETS:{fetch:async request=>new Response('asset:'+new URL(request.url).pathname,{headers:{'Content-Type':'text/plain'}})}};
  const fetcher=async (url,init)=>{
    calls.push({url,init});
    if(options.fetcher)return options.fetcher(url,init);
    const path=new URL(url).pathname,data=init.body?JSON.parse(init.body):{};
    if(path==='/auth/v1/token')return Response.json({access_token:'test.admin.token',refresh_token:'test-refresh',expires_in:3600});
    if(path==='/auth/v1/logout')return new Response(null,{status:204});
    if(path.endsWith('/controlai_me'))return Response.json({id:'u1',nome:'Teste',email:'test@example.test',papel:init.headers.Authorization==='Bearer operator'?'operador':'admin'});
    if(path.endsWith('/controlai_read_state'))return Response.json({revision:3,state:{estoque:[],obras:[],itens:[]}});
    if(path.endsWith('/controlai_write_state'))return Response.json({revision:data.p_revision+1,state:data.p_state});
    if(path.endsWith('/controlai_manage_user'))return Response.json({ok:true,mode:'supabase'});
    return Response.json({});
  };
  const app=createWorker(fetcher);
  const request=async (path,{method='GET',body,token,csrf=true,originHeader=true,headers={}}={})=>{
    const h=new Headers(headers);
    if(body!==undefined)h.set('Content-Type','application/json');
    if(originHeader)h.set('Origin',origin);
    if(token){h.set('Cookie',`ca_access=${token}; ca_csrf=test-csrf`);if(csrf)h.set('X-CSRF-Token','test-csrf');}
    return app.fetch(new Request(origin+path,{method,headers:h,body:body===undefined?undefined:JSON.stringify(body)}),env);
  };
  return {request,env,app,calls};
}
test('assets are public; sources, configuration, database and unknown URLs are blocked',async()=>{
  const {request,calls}=setup();
  for(const path of ['/','/auth.js','/service-worker.js','/manifest.webmanifest','/icons/icon-512.png']){
    const r=await request(path);assert.equal(r.status,200);assert.equal(r.headers.get('Cache-Control'),'no-cache');assert.equal(r.headers.get('X-Frame-Options'),'DENY');
  }
  for(const path of ['/supabase/config.json','/supabase/setup.sql','/server.py','/worker/index.mjs','/.env','/estoque.sqlite3','/unrelated'])assert.equal((await request(path)).status,404);
  assert.equal(calls.length,0);
  assert.equal((await request('/healthz',{method:'HEAD'})).status,200);
  assert.equal(await (await request('/index.html',{method:'HEAD'})).text(),'');
});
test('no session exposes no data, status can open the login screen',async()=>{
  const {request,calls}=setup();
  assert.equal((await request('/api/state')).status,401);
  const status=await request('/api/auth/status');assert.equal(status.status,200);assert.equal((await status.json()).user,null);
  assert.equal(calls.length,0);
});
test('login delegates to Supabase; tokens only go to secure HttpOnly cookies',async()=>{
  const {request,calls}=setup();const r=await request('/api/auth/login',{method:'POST',body:{email:'USER@EXAMPLE.TEST',senha:'test-password'}});
  assert.equal(r.status,200);const data=await r.json();assert.equal(data.user.papel,'admin');assert.ok(data.csrf);assert.equal(data.access_token,undefined);assert.equal(data.refresh_token,undefined);
  const cookies=r.headers.getSetCookie();assert.equal(cookies.length,3);cookies.forEach(c=>{assert.match(c,/HttpOnly/);assert.match(c,/Secure/);assert.match(c,/SameSite=Strict/);});
  const first=calls[0];assert.equal(first.url,'https://testproject.supabase.co/auth/v1/token?grant_type=password');assert.equal(first.init.headers.apikey,'sb_publishable_test');assert.equal(JSON.parse(first.init.body).email,'user@example.test');assert.equal(first.init.redirect,'manual');
});
test('expired tokens refresh through Supabase without persistence in the browser database',async()=>{
  const ctx=setup({fetcher:async(url,init)=>{
    if(url.includes('grant_type=refresh_token'))return Response.json({access_token:'renewed.token',refresh_token:'new-refresh',expires_in:3600});
    if(init.headers.Authorization==='Bearer expired')return Response.json({code:'PGRST301'},{status:401});
    return Response.json({id:'u1',nome:'Teste',papel:'admin'});
  }});
  const r=await ctx.request('/api/auth/status',{headers:{Cookie:'ca_access=expired; ca_refresh=old-refresh; ca_csrf=old'}});
  assert.equal(r.status,200);assert.equal(r.headers.getSetCookie().length,3);assert.ok((await r.json()).csrf);
});
test('mutations require same origin and CSRF',async()=>{
  const {request,calls}=setup(),body={revision:3,state:{obras:[]}};
  assert.equal((await request('/api/state',{method:'PUT',body,token:'admin',csrf:false})).status,403);
  assert.equal((await request('/api/state',{method:'PUT',body,token:'admin',originHeader:false})).status,403);
  assert.equal(calls.length,0);
});
test('admin and operators can save; server-side RPC receives the user token and revision',async()=>{
  const {request,calls}=setup();
  for(const token of ['admin','operator']){
    const response=await request('/api/state',{method:'PUT',body:{revision:3,state:{obras:[{id:1,nome:'Obra'}]}},token});
    assert.equal(response.status,200);assert.equal((await response.json()).revision,4);
    const call=calls.at(-1);assert.equal(call.init.headers.Authorization,'Bearer '+token);assert.equal(JSON.parse(call.init.body).p_restore,false);
  }
  assert.equal((await request('/api/state',{method:'PUT',body:{revision:'3',state:{}},token:'admin'})).status,400);
});
test('operator cannot manage users, read audit/backups, or restore',async()=>{
  const {request}=setup();
  for(const path of ['/api/users','/api/audit','/api/backup'])assert.equal((await request(path,{token:'operator'})).status,403);
  for(const path of ['/api/invitations','/api/users/active','/api/restore'])assert.equal((await request(path,{method:'POST',body:{revision:1,state:{}},token:'operator'})).status,403);
});
test('admin user management and restore keep their existing API contract',async()=>{
  const {request,calls}=setup();
  assert.equal((await request('/api/users',{token:'admin'})).status,200);
  assert.equal((await request('/api/invitations',{method:'POST',token:'admin',body:{nome:'Apoio',email:'apoio@example.test'}})).status,200);
  assert.equal(JSON.parse(calls.at(-1).init.body).p_active,true);
  assert.equal((await request('/api/users/active',{method:'POST',token:'admin',body:{id:'apoio@example.test',ativo:false}})).status,200);
  assert.equal(JSON.parse(calls.at(-1).init.body).p_email,'apoio@example.test');
  assert.equal((await request('/api/restore',{method:'POST',token:'admin',body:{revision:3,state:{estoque:[]}}})).status,200);
  assert.equal(JSON.parse(calls.at(-1).init.body).p_restore,true);
});
test('logout clears cookies and asks Supabase to revoke the refresh session',async()=>{
  const {request,calls}=setup();const r=await request('/api/auth/logout',{method:'POST',token:'admin',body:{}});
  assert.equal(r.status,200);assert.equal(r.headers.getSetCookie().length,3);r.headers.getSetCookie().forEach(c=>assert.match(c,/Max-Age=0/));
  assert.match(calls.at(-1).url,/logout\?scope=local/);
});
test('database failures stay failures; there is no local data fallback',async()=>{
  const {request}=setup({fetcher:async()=>{throw Error('connection failed with private data');}});
  const r=await request('/api/state',{token:'admin'});assert.equal(r.status,503);assert.doesNotMatch(await r.text(),/private data/);
});
test('validation diagnostics do not expose private upstream details',async()=>{
  const {request}=setup({fetcher:async()=>Response.json({code:'42702',message:'private database payload',details:'private details'},{status:400})});
  const r=await request('/api/state',{token:'admin'});assert.equal(r.status,400);const text=await r.text();assert.match(text,/42702/);assert.doesNotMatch(text,/private/);
});
test('request size and JSON checks run before sending data upstream',async()=>{
  const {app,env,calls}=setup();
  const r=await app.fetch(new Request(origin+'/api/auth/login',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json','Content-Length':'10000001'},body:'{}'}),env);
  assert.equal(r.status,413);assert.equal(calls.length,0);
  assert.equal((await app.fetch(new Request(origin+'/api/auth/login',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:'[]'}),env)).status,400);
});
test('build publishes only the explicit static allowlist',async()=>{
  const files=await readdir(new URL('../dist/public/',import.meta.url));assert.ok(files.includes('index.html'));assert.ok(!files.includes('worker'));assert.ok(!files.includes('supabase'));assert.ok(!files.includes('tests'));assert.ok(!files.includes('.env'));
  const page=await readFile(new URL('../dist/public/index.html',import.meta.url),'utf8');assert.match(page,/Salvar alterações/);
});

test('upstream redirects are blocked instead of forwarding credentials to another host',async()=>{
  const {request,calls}=setup({fetcher:async()=>new Response(null,{status:307,headers:{Location:'https://other.example/private'}})});
  const response=await request('/api/auth/login',{method:'POST',body:{email:'test@example.test',senha:'test-password'}});
  assert.equal(response.status,502);assert.equal(calls.length,1);assert.match(calls[0].url,/^https:\/\/testproject\.supabase\.co\//);
  assert.doesNotMatch(await response.text(),/other\.example/);
});
