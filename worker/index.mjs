import project from '../supabase/config.json' with {type:'json'};

const PUBLIC_PATHS = new Set(['/', '/index.html', '/auth.js', '/auth.css', '/storage.js', '/pedidos.js', '/manifest.webmanifest', '/pwa.js', '/service-worker.js', '/icons/icon-180.png', '/icons/icon-192.png', '/icons/icon-512.png']);
const LIMIT = 10_000_000;
class ApiError extends Error {
  constructor(status,message) { super(message);this.status=status; }
}
const validation = new Map([
  ['Identificador duplicado','O cadastro contém identificadores repetidos. Atualize o app antes de cadastrar novamente.'],
  ['Identificador inválido','O cadastro tem um identificador inválido.'],
  ['Histórico não pode ser excluído','Uma alteração tentou remover pedidos ou entregas do histórico.'],
  ['Entregas não podem ser editadas','Uma entrega já registrada não pode ser modificada.'],
  ['Preserve os dados históricos do pedido','Uma alteração tentou modificar dados históricos de um pedido.'],
  ['Entrega excede a quantidade pendente','A quantidade entregue ultrapassa o total solicitado.'],
  ['Quantidade entregue inválida','Informe uma quantidade inteira maior que zero.'],
]);
function safeResponse(body,status=200,cookies=[]) {
  const headers=new Headers({'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer'});
  cookies.forEach(c=>headers.append('Set-Cookie',c));
  return new Response(JSON.stringify(body),{status,headers});
}
function readCookies(request) {
  const result={};
  for(const part of (request.headers.get('Cookie')||'').split(';')) {
    const at=part.indexOf('=');if(at<0)continue;
    result[part.slice(0,at).trim()]=part.slice(at+1).trim();
  }
  return result;
}
function randomToken() {return Array.from(crypto.getRandomValues(new Uint8Array(32)),v=>v.toString(16).padStart(2,'0')).join('');}
function constantEqual(a,b) {
  if(typeof a!=='string'||typeof b!=='string'||a.length!==b.length)return false;
  let difference=0;for(let i=0;i<a.length;i++)difference|=a.charCodeAt(i)^b.charCodeAt(i);
  return difference===0;
}
function cookie(request,name,value,maxAge=43200) {
  if(value&&!/^[A-Za-z0-9._~-]+$/.test(value))throw new ApiError(401,'Sessão inválida. Entre novamente.');
  return `${name}=${value}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${maxAge}${new URL(request.url).protocol==='https:'?'; Secure':''}`;
}
const clearCookies=request=>['ca_access','ca_refresh','ca_csrf'].map(name=>cookie(request,name,'',0));
function authorizeOrigin(request,csrf=true) {
  if(request.headers.get('Origin')!==new URL(request.url).origin)throw new ApiError(403,'Origem não permitida.');
  const secret=readCookies(request).ca_csrf;
  if(csrf&&(!secret||!constantEqual(secret,request.headers.get('X-CSRF-Token'))))throw new ApiError(403,'Recarregue a página antes de continuar.');
}
async function bodyJson(request) {
  if(request.headers.get('Content-Type')?.split(';')[0].trim()!=='application/json')throw new ApiError(400,'Envie uma requisição JSON.');
  if(Number(request.headers.get('Content-Length'))>LIMIT)throw new ApiError(413,'A alteração excede o tamanho máximo permitido.');
  const reader=request.body?.getReader();if(!reader)throw new ApiError(400,'Requisição inválida.');
  const chunks=[];let size=0;
  while(true) {
    const {done,value}=await reader.read();if(done)break;
    size+=value.byteLength;
    if(size>LIMIT){await reader.cancel();throw new ApiError(413,'A alteração excede o tamanho máximo permitido.');}
    chunks.push(value);
  }
  try {
    const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
    const result=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
    if(!result||typeof result!=='object'||Array.isArray(result))throw Error();
    return result;
  }catch{throw new ApiError(400,'Requisição inválida.');}
}
function supabase(env,fetcher) {
  const base=env.SUPABASE_URL||project.url,key=env.SUPABASE_PUBLISHABLE_KEY||project.publishable_key;
  const target=new URL(base);
  if(target.protocol!=='https:'||!target.hostname.endsWith('.supabase.co')||target.username||target.password||!['','/'].includes(target.pathname)||target.search||target.hash||(target.port&&target.port!=='443')||!key.startsWith('sb_publishable_'))throw new ApiError(503,'Configuração pública do Supabase inválida.');
  async function call(path,data=undefined,token=undefined) {
    const headers={'apikey':key,'Accept':'application/json'};
    if(token)headers.Authorization='Bearer '+token;
    if(data!==undefined)headers['Content-Type']='application/json';
    let response;
    try{response=await fetcher(target.origin+path,{method:data===undefined?'GET':'POST',headers,body:data===undefined?undefined:JSON.stringify(data),redirect:'manual',signal:AbortSignal.timeout(30000)});}
    catch{throw new ApiError(503,'Não foi possível conectar ao Supabase. Nenhum dado foi salvo localmente.');}
    // Workers aceita somente manual/follow. Nunca seguir Location com credenciais.
    if(response.status>=300&&response.status<400){
      console.warn('supabase_redirect_blocked',{operation:path.split('?')[0],status:response.status});
      throw new ApiError(502,'O Supabase retornou um redirecionamento inesperado. A conexão não foi seguida.');
    }
    let result={};
    const raw=await response.text();
    if(raw){try{result=JSON.parse(raw);}catch{throw new ApiError(502,'Resposta inválida do Supabase.');}}
    if(response.ok)return result;
    const code=/^[A-Z0-9]{5,12}$/.test(String(result?.code))?String(result.code):'UNKNOWN';
    console.warn('supabase_failure',{operation:path.split('?')[0],status:response.status,code});
    if(code==='P0001'&&validation.has(result?.message))throw new ApiError(400,validation.get(result.message)+' (código '+code+')');
    if(['PGRST202','PGRST205','42883','42P01'].includes(code))throw new ApiError(503,'Execute supabase/setup.sql no SQL Editor deste projeto antes de continuar.');
    if(response.status===429)throw new ApiError(429,'Muitas tentativas. Aguarde antes de tentar novamente.');
    if([400,401,403].includes(response.status)&&path.startsWith('/auth/'))throw new ApiError(401,'E-mail ou senha inválidos, ou conta não confirmada no Supabase.');
    if([401,403,409].includes(response.status))throw new ApiError(response.status,({401:'Entre na sua conta para continuar.',403:'Esta conta não está autorizada para esta operação.',409:'Outra sessão alterou os dados. Recarregue a página.'})[response.status]);
    throw new ApiError(response.status===400?400:502,`Não foi possível salvar no Supabase (código ${code}). Informe esse código para investigarmos; os dados existentes foram preservados.`);
  }
  return {call,rpc:(name,token,parameters={})=>call('/rest/v1/rpc/'+name,parameters,token)};
}
async function session(request,remote) {
  const token=readCookies(request).ca_access;if(!token)throw new ApiError(401,'Entre na sua conta para continuar.');
  const user=await remote.rpc('controlai_me',token);
  return {token,user};
}
function requireAdmin(user) {if(user.papel!=='admin')throw new ApiError(403,'Apenas o administrador pode acessar esta função.');}
async function finishLogin(request,remote,result) {
  if(!result.access_token||!result.refresh_token)throw new ApiError(401,'Confirme sua conta no Supabase antes de entrar.');
  const user=await remote.rpc('controlai_me',result.access_token),csrf=randomToken();
  const age=Number(result.expires_in);
  return safeResponse({provider:'supabase',user,csrf},200,[cookie(request,'ca_access',result.access_token,Number.isFinite(age)&&age>0?Math.min(Math.floor(age),43200):3600),cookie(request,'ca_refresh',result.refresh_token),cookie(request,'ca_csrf',csrf)]);
}
async function authStatus(request,remote) {
  const cookies=readCookies(request);
  if(cookies.ca_access) {
    try{
      const user=await remote.rpc('controlai_me',cookies.ca_access),csrf=cookies.ca_csrf||randomToken();
      return safeResponse({provider:'supabase',setupRequired:false,user,csrf},200,[cookie(request,'ca_csrf',csrf)]);
    }catch(error){if(error.status!==401)throw error;}
  }
  if(cookies.ca_refresh) {
    try{return await finishLogin(request,remote,await remote.call('/auth/v1/token?grant_type=refresh_token',{refresh_token:cookies.ca_refresh}));}
    catch(error){if(error.status!==401)throw error;}
  }
  return safeResponse({provider:'supabase',setupRequired:false,user:null,csrf:null},200,clearCookies(request));
}
async function writeState(request,remote,token,data,restore=false) {
  if(!Number.isSafeInteger(data.revision)||!data.state||typeof data.state!=='object'||Array.isArray(data.state))throw new ApiError(400,'Dados inválidos.');
  return safeResponse(await remote.rpc('controlai_write_state',token,{p_revision:data.revision,p_state:data.state,p_restore:restore}));
}
export function createWorker(fetcher=(...args)=>fetch(...args)) {
  return {async fetch(request,env) {
    const url=new URL(request.url),path=url.pathname,method=request.method;
    try{
      let response;
      if(['GET','HEAD'].includes(method)) {
        if(path==='/healthz')response=safeResponse({status:'ok',backend:'supabase',hosting:'cloudflare'});
        else if(PUBLIC_PATHS.has(path)) {
          response=await env.ASSETS.fetch(new Request(request,{method:'GET'}));
          const headers=new Headers(response.headers);
          headers.set('Cache-Control','no-cache');headers.set('X-Content-Type-Options','nosniff');headers.set('X-Frame-Options','DENY');headers.set('Referrer-Policy','no-referrer');
          response=new Response(response.body,{status:response.status,headers});
        }else if(path==='/api/auth/status')response=await authStatus(request,supabase(env,fetcher));
        else if(['/api/state','/api/backup','/api/users','/api/audit'].includes(path)) {
          const remote=supabase(env,fetcher),{token,user}=await session(request,remote);
          if(path!=='/api/state')requireAdmin(user);
          const name=path==='/api/users'?'controlai_list_users':path==='/api/audit'?'controlai_get_audit':'controlai_read_state';
          response=safeResponse(await remote.rpc(name,token,name==='controlai_read_state'?{p_backup:path==='/api/backup'}:{}));
        }else response=safeResponse({error:'Não encontrado.'},404);
        return method==='HEAD'?new Response(null,{status:response.status,headers:response.headers}):response;
      }
      if(!['POST','PUT'].includes(method))return safeResponse({error:'Método não permitido.'},405);
      const login=path==='/api/auth/login'&&method==='POST';authorizeOrigin(request,!login);
      const data=await bodyJson(request),remote=supabase(env,fetcher);
      if(login) {
        if(typeof data.email!=='string'||data.email.length>254||typeof data.senha!=='string'||data.senha.length<1||data.senha.length>128)throw new ApiError(400,'Confira o e-mail e a senha.');
        return await finishLogin(request,remote,await remote.call('/auth/v1/token?grant_type=password',{email:data.email.trim().toLowerCase(),password:data.senha}));
      }
      if(path==='/api/auth/logout'&&method==='POST') {
        const token=readCookies(request).ca_access;
        if(token){try{await remote.call('/auth/v1/logout?scope=local',{},token);}catch(error){if(error.status!==401)throw error;}}
        return safeResponse({ok:true},200,clearCookies(request));
      }
      const {token,user}=await session(request,remote);
      if(path==='/api/state'&&method==='PUT')return await writeState(request,remote,token,data);
      if(method==='POST'&&['/api/restore','/api/invitations','/api/users/active','/api/invitations/revoke'].includes(path)) {
        requireAdmin(user);
        if(path==='/api/restore')return await writeState(request,remote,token,data,true);
        if(path==='/api/invitations')return safeResponse(await remote.rpc('controlai_manage_user',token,{p_email:data.email,p_name:data.nome,p_active:true}));
        if(path==='/api/users/active') {
          if(typeof data.ativo!=='boolean')throw new ApiError(400,'Informe o estado do acesso.');
          return safeResponse(await remote.rpc('controlai_manage_user',token,{p_email:data.id,p_name:null,p_active:data.ativo}));
        }
        throw new ApiError(400,'No modo Supabase, gerencie a autorização na lista de usuários.');
      }
      return safeResponse({error:'Não encontrado.'},404);
    }catch(error){
      if(error instanceof ApiError)return safeResponse({error:error.message},error.status);
      console.error('worker_failure',{type:error?.name||'Error'});
      return safeResponse({error:'Não foi possível concluir a operação.'},500);
    }
  }};
}
export default createWorker();
