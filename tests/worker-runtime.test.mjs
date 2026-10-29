// Exercita o bundle real no workerd. Nenhuma chamada usa uma conta Supabase real.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {Miniflare,convertV4MiniflareOptions} from 'miniflare';

test('Supabase login works in the actual Workers runtime and blocks redirects',async()=>{
  const script=await readFile(new URL('../dist/worker-check/index.js',import.meta.url),'utf8');
  let mode='success';const calls=[];
  const runtime=new Miniflare(convertV4MiniflareOptions({
    modules:true,script,compatibilityDate:'2026-10-29',
    bindings:{SUPABASE_URL:'https://testproject.supabase.co',SUPABASE_PUBLISHABLE_KEY:'sb_publishable_test'},
    outboundService:async request=>{
      const url=new URL(request.url);calls.push(url.origin+url.pathname);
      assert.equal(url.origin,'https://testproject.supabase.co');
      if(mode==='redirect')return new Response(null,{status:307,headers:{Location:'https://other.example/blocked'}});
      if(mode==='invalid')return Response.json({code:'invalid_credentials',message:'Invalid login credentials'},{status:400});
      if(url.pathname==='/auth/v1/token')return Response.json({access_token:'synthetic.access.token',refresh_token:'synthetic-refresh',expires_in:3600});
      if(url.pathname==='/rest/v1/rpc/controlai_me')return Response.json({id:'test-user',nome:'Runtime Test',papel:'admin'});
      throw Error('Unexpected endpoint');
    },
  }));
  const login=()=>runtime.dispatchFetch('https://test-worker.example/api/auth/login',{method:'POST',headers:{Origin:'https://test-worker.example','Content-Type':'application/json'},body:JSON.stringify({email:'test@example.test',senha:'synthetic-test-password'})});
  try{
    const success=await login();assert.equal(success.status,200,await success.clone().text());
    const data=await success.json();assert.equal(data.user.nome,'Runtime Test');assert.ok(data.csrf);
    assert.equal(data.access_token,undefined);assert.equal(data.refresh_token,undefined);
    const cookies=success.headers.getSetCookie();assert.equal(cookies.length,3);cookies.forEach(c=>{assert.match(c,/HttpOnly/);assert.match(c,/Secure/);});
    assert.deepEqual(calls,['https://testproject.supabase.co/auth/v1/token','https://testproject.supabase.co/rest/v1/rpc/controlai_me']);
    mode='invalid';const invalid=await login();assert.equal(invalid.status,401);
    const before=calls.length;mode='redirect';const redirect=await login();assert.equal(redirect.status,502);
    assert.equal(calls.length,before+1);assert.doesNotMatch(await redirect.text(),/other\.example/);
  }finally{await runtime.dispose();}
});
