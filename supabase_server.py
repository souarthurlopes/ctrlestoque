"""Ponte HTTPS Supabase. Chave pública, tokens de usuário e cookies HttpOnly.
Não utiliza service_role nem salva estado/senhas em disco.
"""
import json
import os
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent

class RemoteError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status

class Supabase:
    def __init__(self, config=None):
        config = config or json.loads((ROOT/'supabase/config.json').read_text())
        self.url = os.environ.get('SUPABASE_URL', config['url']).rstrip('/')
        self.key = os.environ.get('SUPABASE_PUBLISHABLE_KEY', config['publishable_key'])
        parsed = urlsplit(self.url)
        if parsed.scheme != 'https' or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.port not in (None,443) or not parsed.hostname or not parsed.hostname.endswith('.supabase.co'):
            raise ValueError('Configure uma URL HTTPS de projeto Supabase, sem /rest/v1/.')
        if not self.key.startswith('sb_publishable_'):
            raise ValueError('Use somente a chave pública publishable do projeto.')

    def request(self, path, data=None, token=None):
        headers = {'apikey':self.key, 'Accept':'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        body = None
        if data is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(data, allow_nan=False).encode()
        request = urllib.request.Request(self.url+path, data=body, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            try:
                result = json.loads(error.read())
            except (ValueError, OSError):
                result = {}
            code = result.get('code', '')
            if code in ('PGRST202','PGRST205','42883','42P01'):
                raise RemoteError(503, 'Execute supabase/setup.sql no SQL Editor deste projeto antes de continuar.') from None
            if error.code == 429:
                raise RemoteError(429, 'Muitas tentativas. Aguarde antes de tentar novamente.') from None
            if error.code in (400,401,403) and path.startswith('/auth/'):
                raise RemoteError(401, 'E-mail ou senha inválidos, ou conta não confirmada no Supabase.') from None
            if error.code in (401,403,409):
                message = {401:'Entre na sua conta para continuar.',403:'Esta conta não está autorizada para esta operação.',409:'Outra sessão alterou os dados. Recarregue a página.'}[error.code]
                raise RemoteError(error.code, message) from None
            raise RemoteError(400 if error.code == 400 else 502, 'O Supabase recusou a alteração. Confira os campos, as quantidades e preserve o histórico.') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RemoteError(503, 'Não foi possível conectar ao Supabase. Nenhum dado foi salvo localmente.') from None

    def rpc(self, name, token, **parameters):
        return self.request('/rest/v1/rpc/'+name, parameters, token)

class Handler(SimpleHTTPRequestHandler):
    backend = None
    secure_cookie = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        super().end_headers()

    def reply(self, status, data, cookies=()):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(payload)))
        for cookie in cookies:
            self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(payload)

    def cookies(self):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie',''))
        except Exception:
            return {}
        return {k:v.value for k,v in cookies.items()}

    def cookie(self, name, value, max_age=43200):
        return f'{name}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}' + ('; Secure' if self.secure_cookie else '')

    def clear_cookies(self):
        return [self.cookie(name,'',0) for name in ('ca_access','ca_refresh','ca_csrf')]

    def session(self):
        token = self.cookies().get('ca_access')
        if not token:
            raise RemoteError(401,'Entre na sua conta para continuar.')
        user = self.backend.rpc('controlai_me',token)
        return token, user

    def body(self):
        try:
            size = int(self.headers.get('Content-Length','0'))
            if not 0<size<=10_000_000 or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                raise ValueError()
            data = json.loads(self.rfile.read(size))
            if not isinstance(data,dict):
                raise ValueError()
            return data
        except (ValueError,TypeError):
            raise RemoteError(400,'Requisição inválida.') from None

    def authorize_origin(self, csrf=True):
        origin = urlsplit(self.headers.get('Origin',''))
        if origin.scheme not in ('https','http') or origin.netloc!=self.headers.get('Host'):
            raise RemoteError(403,'Origem não permitida.')
        secret = self.cookies().get('ca_csrf','')
        if csrf and (not secret or not secrets.compare_digest(secret,self.headers.get('X-CSRF-Token',''))):
            raise RemoteError(403,'Recarregue a página antes de continuar.')

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            if path == '/api/auth/status':
                return self.status()
            if path in ('/api/state','/api/backup','/api/users','/api/audit'):
                token,user = self.session()
                if path == '/api/state':
                    result = self.backend.rpc('controlai_read_state',token,p_backup=False)
                else:
                    if user['papel']!='admin':
                        raise RemoteError(403,'Apenas o administrador pode acessar esta função.')
                    if path == '/api/backup':
                        result = self.backend.rpc('controlai_read_state',token,p_backup=True)
                    else:
                        result = self.backend.rpc('controlai_list_users' if path=='/api/users' else 'controlai_get_audit',token)
                return self.reply(200,result)
            if path not in ('/','/index.html','/auth.js','/auth.css','/storage.js','/pedidos.js'):
                return self.reply(404,dict(error='Não encontrado.'))
            return super().do_GET()
        except RemoteError as error:
            return self.reply(error.status,dict(error=str(error)))

    def status(self):
        cookies = self.cookies()
        session = None
        token = cookies.get('ca_access')
        if token:
            try:
                user = self.backend.rpc('controlai_me',token)
                csrf = cookies.get('ca_csrf') or secrets.token_urlsafe(32)
                return self.reply(200,dict(provider='supabase',setupRequired=False,user=user,csrf=csrf),[self.cookie('ca_csrf',csrf)])
            except RemoteError as error:
                if error.status!=401:
                    raise
        if cookies.get('ca_refresh'):
            try:
                session = self.backend.request('/auth/v1/token?grant_type=refresh_token',dict(refresh_token=cookies['ca_refresh']))
            except RemoteError as error:
                if error.status!=401:
                    raise
        if session:
            return self.finish_login(session)
        return self.reply(200,dict(provider='supabase',setupRequired=False,user=None,csrf=None),self.clear_cookies())

    def finish_login(self, session):
        access = session.get('access_token')
        refresh = session.get('refresh_token')
        if not access or not refresh:
            raise RemoteError(401,'Confirme sua conta no Supabase antes de entrar.')
        user = self.backend.rpc('controlai_me',access)
        csrf = secrets.token_urlsafe(32)
        cookies = [self.cookie('ca_access',access,min(int(session.get('expires_in',3600)),43200)),self.cookie('ca_refresh',refresh),self.cookie('ca_csrf',csrf)]
        return self.reply(200,dict(provider='supabase',user=user,csrf=csrf),cookies)

    def do_POST(self):
        try:
            login = self.path == '/api/auth/login'
            self.authorize_origin(csrf=not login)
            data = self.body()
            if login:
                email, password = data.get('email'),data.get('senha')
                if not isinstance(email,str) or not isinstance(password,str) or len(email)>254 or not 1<=len(password)<=128:
                    raise RemoteError(400,'Confira o e-mail e a senha.')
                return self.finish_login(self.backend.request('/auth/v1/token?grant_type=password',dict(email=email.strip().lower(),password=password)))
            if self.path == '/api/auth/logout':
                token = self.cookies().get('ca_access')
                if token:
                    try:
                        self.backend.request('/auth/v1/logout?scope=local',{},token)
                    except RemoteError as error:
                        if error.status!=401:
                            raise
                return self.reply(200,dict(ok=True),self.clear_cookies())
            token,user = self.session()
            if self.path in ('/api/restore','/api/invitations','/api/users/active','/api/invitations/revoke'):
                if user['papel']!='admin':
                    raise RemoteError(403,'Apenas administrador.')
                if self.path == '/api/restore':
                    return self.write_state(token,data,restore=True)
                if self.path == '/api/invitations':
                    result = self.backend.rpc('controlai_manage_user',token,p_email=data.get('email'),p_name=data.get('nome'),p_active=True)
                elif self.path == '/api/users/active':
                    if type(data.get('ativo')) is not bool:
                        raise RemoteError(400,'Informe o estado do acesso.')
                    result = self.backend.rpc('controlai_manage_user',token,p_email=data.get('id'),p_name=None,p_active=data['ativo'])
                else:
                    raise RemoteError(400,'No modo Supabase, gerencie a autorização na lista de usuários.')
                return self.reply(200,result)
            raise RemoteError(404,'Não encontrado.')
        except RemoteError as error:
            return self.reply(error.status,dict(error=str(error)))

    def write_state(self, token, data, restore=False):
        if type(data.get('revision')) is not int or not isinstance(data.get('state'),dict):
            raise RemoteError(400,'Dados inválidos.')
        result = self.backend.rpc('controlai_write_state',token,p_revision=data['revision'],p_state=data['state'],p_restore=restore)
        return self.reply(200,result)

    def do_PUT(self):
        try:
            self.authorize_origin()
            token,_ = self.session()
            if self.path!='/api/state':
                raise RemoteError(404,'Não encontrado.')
            return self.write_state(token,self.body())
        except RemoteError as error:
            return self.reply(error.status,dict(error=str(error)))

def serve():
    Handler.backend = Supabase()
    Handler.secure_cookie = os.environ.get('CONTROLAI_SECURE_COOKIE')=='1'
    port = int(os.environ.get('CONTROLAI_PORT','8081'))
    print(f'ControlAI: backend Supabase, servidor local na porta {port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
