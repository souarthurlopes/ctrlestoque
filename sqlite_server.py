"""ControlAI: servidor de desenvolvimento autenticado com persistência SQLite."""
import json
import os
import secrets
import sqlite3
import sys
import time
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import auth

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('CONTROLAI_DB', '/workspace/controlai-data/estoque.sqlite3'))
DB.parent.mkdir(parents=True, exist_ok=True)
SECURE_COOKIE = os.environ.get('CONTROLAI_SECURE_COOKIE') == '1'
INITIAL = dict(estoque=[], dataEst='', obras=[], itens=[], nid=1, pedidos=[], entregas=[])
with sqlite3.connect(DB) as c:
    c.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, payload TEXT NOT NULL)')
    c.execute('INSERT OR IGNORE INTO state VALUES (1, 0, ?)', (json.dumps(INITIAL),))
auth.initialize(DB)

def validate_state(state):
    if not isinstance(state, dict) or any(not isinstance(state.get(k), list) for k in ('estoque', 'obras', 'itens')):
        raise ValueError('Estrutura inválida.')
    for key in ('pedidos', 'entregas', 'obras', 'itens'):
        rows = state.get(key, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get('id'), (str, int)) for row in rows):
            raise ValueError('Registros inválidos.')
        if len({str(r['id']) for r in rows}) != len(rows):
            raise ValueError('Identificadores duplicados.')
    for p in state.get('pedidos', []):
        if not isinstance(p.get('linhas'), list) or not p['linhas']:
            raise ValueError('Pedido sem equipamentos.')
        if len({l.get('id') for l in p['linhas']}) != len(p['linhas']):
            raise ValueError('Itens duplicados.')
        if any(not isinstance(l.get('qtd'), int) or isinstance(l['qtd'], bool) or l['qtd'] < 1 for l in p['linhas']):
            raise ValueError('Quantidade inválida.')
    totals = {}
    for e in state.get('entregas', []):
        if not isinstance(e.get('qtd'), int) or isinstance(e['qtd'], bool) or e['qtd'] < 1:
            raise ValueError('Quantidade entregue inválida.')
        line = next((l for p in state.get('pedidos', []) if p['id'] == e.get('pedidoId') for l in p['linhas'] if l['id'] == e.get('linhaId')), None)
        if not line:
            raise ValueError('Entrega sem item de pedido correspondente.')
        key = (e['pedidoId'], e['linhaId'])
        totals[key] = totals.get(key, 0) + e['qtd']
        if totals[key] > line['qtd']:
            raise ValueError('A entrega excede a quantidade solicitada.')

def annotate(old, new, user, restore=False):
    actor = dict(id=user['id'], nome=user['name'])
    details = []
    for key in ('obras', 'itens', 'pedidos', 'entregas'):
        previous = {str(r['id']): r for r in old.get(key, [])}
        current = {str(r['id']): r for r in new.get(key, [])}
        for id, row in current.items():
            for field in ('criadoPor', 'atualizadoPor', 'registradoEmServidor'):
                if id in previous and field in previous[id]:
                    row[field] = previous[id][field]
                else:
                    row.pop(field, None)
        if not restore and key in ('pedidos', 'entregas'):
            for id, row in previous.items():
                if id not in current:
                    raise ValueError('Pedidos e entregas não podem ser excluídos; preserve o histórico.')
                candidate = current[id]
                if key == 'entregas' and candidate != row:
                    raise ValueError('Uma entrega registrada não pode ser editada.')
                if key == 'pedidos':
                    # Pode acrescentar linhas; as já registradas são preservadas.
                    base = lambda r: {k: v for k, v in r.items() if k not in ('linhas', 'atualizadoPor')}
                    if base(candidate) != base(row) or any(l not in candidate['linhas'] for l in row['linhas']):
                        raise ValueError('Os dados históricos do pedido não podem ser alterados.')
        for id, row in current.items():
            original = previous.get(id)
            if row != original or restore:
                row['criadoPor'] = original.get('criadoPor', actor) if original else actor
                row['atualizadoPor'] = actor
                if not original:
                    row['registradoEmServidor'] = int(time.time())
                details.append(dict(tipo=key, id=id, acao='alterado' if original else 'criado'))
        for id in previous.keys() - current.keys():
            details.append(dict(tipo=key, id=id, acao='removido'))
    if old.get('estoque') != new.get('estoque'):
        details.append(dict(tipo='estoque', acao='importado', quantidade=len(new.get('estoque', []))))
    return details

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def reply(self, code, value, cookie=None):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(data)))
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        size = int(self.headers.get('Content-Length', '0'))
        if not 0 < size <= 10_000_000:
            raise ValueError('Tamanho da requisição inválido.')
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            raise ValueError('Envie JSON.')
        result = json.loads(self.rfile.read(size))
        if not isinstance(result, dict):
            raise ValueError('Dados inválidos.')
        return result

    def session(self):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
        except Exception:
            return None
        token = cookies.get('controlai_session')
        if not token:
            return None
        with auth.connect(DB) as c:
            row = c.execute('SELECT u.*,s.csrf,s.token AS session_token FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.active=1', (auth.digest(token.value), int(time.time()))).fetchone()
        return row

    def authorize(self, admin=False, mutate=False):
        user = self.session()
        if not user:
            self.reply(401, dict(error='Entre na sua conta para continuar.'))
            return None
        if admin and user['role'] != 'admin':
            self.reply(403, dict(error='Esta ação é exclusiva do administrador.'))
            return None
        if mutate and not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), user['csrf']):
            self.reply(403, dict(error='Sessão inválida. Recarregue a página.'))
            return None
        return user

    def same_origin(self):
        origin = self.headers.get('Origin', '')
        parsed = urlsplit(origin)
        if parsed.scheme not in ('http', 'https') or parsed.netloc != self.headers.get('Host'):
            self.reply(403, dict(error='Origem não permitida.'))
            return False
        return True

    def create_session(self, user):
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        now = int(time.time())
        with auth.connect(DB) as c:
            c.execute('DELETE FROM sessions WHERE expires<=?', (now,))
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)', (auth.digest(token), user['id'], csrf, now + auth.SESSION_SECONDS))
            auth.audit(c, user, 'login', {})
        cookie = f'controlai_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={auth.SESSION_SECONDS}'
        if SECURE_COOKIE:
            cookie += '; Secure'
        self.reply(200, dict(user=auth.public_user(user), csrf=csrf), cookie)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/auth/status':
            with auth.connect(DB) as c:
                setup = not c.execute('SELECT 1 FROM users LIMIT 1').fetchone()
            user = self.session()
            return self.reply(200, dict(setupRequired=setup, user=auth.public_user(user) if user else None, csrf=user['csrf'] if user else None))
        if path in ('/api/state', '/api/backup'):
            if not self.authorize(admin=path == '/api/backup'):
                return
            with auth.connect(DB) as c:
                row = c.execute('SELECT revision,payload FROM state WHERE id=1').fetchone()
            return self.reply(200, dict(revision=row['revision'], state=json.loads(row['payload'])))
        if path == '/api/users':
            if not self.authorize(admin=True):
                return
            with auth.connect(DB) as c:
                users = [dict(id=r['id'], nome=r['name'], email=r['email'], papel=r['role'], ativo=bool(r['active'])) for r in c.execute('SELECT * FROM users')]
                invitations = [dict(nome=r['name'], email=r['email'], expira=r['expires']) for r in c.execute('SELECT * FROM invitations WHERE used=0 AND expires>?', (int(time.time()),))]
            return self.reply(200, dict(users=users, invitations=invitations))
        if path == '/api/audit':
            if not self.authorize(admin=True):
                return
            with auth.connect(DB) as c:
                rows = [dict(id=r['id'], em=r['at'], usuario=r['actor'], acao=r['action'], detalhes=json.loads(r['details'])) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')]
            return self.reply(200, dict(registros=rows))
        if path not in ('/', '/index.html', '/pedidos.js', '/storage.js', '/auth.js', '/auth.css'):
            return self.reply(404, dict(error='Não encontrado'))
        return super().do_GET()

    def do_POST(self):
        if not self.same_origin():
            return
        try:
            data = self.body()
            if self.path in ('/api/auth/setup', '/api/auth/accept', '/api/auth/login'):
                return self.public_auth(data)
            user = self.authorize(admin=self.path in ('/api/invitations', '/api/users/active', '/api/restore'), mutate=True)
            if not user:
                return
            if self.path == '/api/auth/logout':
                with auth.connect(DB) as c:
                    c.execute('DELETE FROM sessions WHERE token=?', (user['session_token'],))
                    auth.audit(c, user, 'logout', {})
                return self.reply(200, dict(ok=True), 'controlai_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0' + ('; Secure' if SECURE_COOKIE else ''))
            if self.path == '/api/invitations':
                name, email = auth.identity(data.get('nome'), data.get('email'))
                token = secrets.token_urlsafe(32)
                now = int(time.time())
                with auth.connect(DB) as c:
                    c.execute('BEGIN IMMEDIATE')
                    if c.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone():
                        raise ValueError('Já existe uma conta com este e-mail.')
                    count = c.execute('SELECT COUNT(*) FROM users WHERE active=1').fetchone()[0]
                    pending = c.execute('SELECT COUNT(*) FROM invitations WHERE used=0 AND expires>? AND email<>?', (now, email)).fetchone()[0]
                    if count + pending >= 3:
                        raise ValueError('Os três acessos já estão ocupados. Revogue um convite ou desative uma conta antes de continuar.')
                    c.execute('DELETE FROM invitations WHERE email=?', (email,))
                    c.execute('INSERT INTO invitations VALUES(?,?,?,?,0)', (auth.digest(token), name, email, now + 48 * 3600))
                    auth.audit(c, user, 'convite_criado', dict(email=email))
                return self.reply(201, dict(token=token, expires=now + 48 * 3600))
            if self.path == '/api/invitations/revoke':
                if user['role'] != 'admin':
                    return self.reply(403, dict(error='Apenas administrador.'))
                with auth.connect(DB) as c:
                    c.execute('DELETE FROM invitations WHERE email=? AND used=0', (data.get('email'),))
                    auth.audit(c, user, 'convite_revogado', dict(email=data.get('email')))
                return self.reply(200, dict(ok=True))
            if self.path == '/api/users/active':
                if type(data.get('ativo')) is not bool:
                    raise ValueError('Informe o estado do acesso.')
                with auth.connect(DB) as c:
                    c.execute('BEGIN IMMEDIATE')
                    target = c.execute('SELECT * FROM users WHERE id=?', (data.get('id'),)).fetchone()
                    if not target or target['role'] == 'admin':
                        raise ValueError('A conta do administrador não pode ser desativada por esta tela.')
                    if data['ativo'] and not target['active']:
                        count = c.execute('SELECT COUNT(*) FROM users WHERE active=1').fetchone()[0]
                        pending = c.execute('SELECT COUNT(*) FROM invitations WHERE used=0 AND expires>?', (int(time.time()),)).fetchone()[0]
                        if count + pending >= 3:
                            raise ValueError('Os três acessos estão ocupados.')
                    c.execute('UPDATE users SET active=? WHERE id=?', (int(data['ativo']), target['id']))
                    c.execute('DELETE FROM sessions WHERE user_id=?', (target['id'],))
                    auth.audit(c, user, 'acesso_alterado', dict(email=target['email'], ativo=data['ativo']))
                return self.reply(200, dict(ok=True))
            if self.path == '/api/restore':
                return self.write_state(user, data, restore=True)
            return self.reply(404, dict(error='Não encontrado'))
        except (ValueError, KeyError, TypeError, sqlite3.IntegrityError):
            # Mensagens de validação sem conteúdo de credenciais ou SQL.
            return self.reply(400, dict(error='Não foi possível concluir. Confira os campos, as quantidades e os limites de acesso.'))

    def public_auth(self, data):
        now = int(time.time())
        email = data.get('email', '')
        if not isinstance(email, str):
            raise ValueError('E-mail inválido.')
        # Limite por cliente e por e-mail, persistido no banco.
        identities = [auth.digest(self.client_address[0]), auth.digest(email.lower())]
        with auth.connect(DB) as c:
            c.execute('DELETE FROM auth_attempts WHERE at<?', (now - 900,))
            if any(c.execute('SELECT COUNT(*) FROM auth_attempts WHERE identity=?', (i,)).fetchone()[0] >= 10 for i in identities):
                return self.reply(429, dict(error='Muitas tentativas. Aguarde 15 minutos.'))
            c.executemany('INSERT INTO auth_attempts VALUES(?,?)', [(i, now) for i in identities])
        if self.path == '/api/auth/login':
            with auth.connect(DB) as c:
                user = c.execute('SELECT * FROM users WHERE email=? AND active=1', (email.strip().lower(),)).fetchone()
            if not user or not auth.password_check(data.get('senha'), user['password']):
                # Mesmo custo de hash para e-mails inexistentes.
                if not user:
                    auth.password_check('invalid-password', '00' * 16 + ':' + '00' * 64)
                return self.reply(401, dict(error='E-mail ou senha inválidos.'))
        else:
            hashed = auth.password_hash(data.get('senha'))
            with auth.connect(DB) as c:
                c.execute('BEGIN IMMEDIATE')
                if self.path == '/api/auth/setup':
                    setting = c.execute("SELECT value FROM settings WHERE key='activation'").fetchone()
                    if c.execute('SELECT 1 FROM users LIMIT 1').fetchone() or not setting or not secrets.compare_digest(auth.digest(str(data.get('codigo', ''))), setting['value']):
                        return self.reply(403, dict(error='Código de ativação inválido ou já utilizado.'))
                    name, email = auth.identity(data.get('nome'), email)
                    role = 'admin'
                    c.execute("DELETE FROM settings WHERE key='activation'")
                else:
                    invite = c.execute('SELECT * FROM invitations WHERE token=? AND used=0 AND expires>?', (auth.digest(str(data.get('token', ''))), now)).fetchone()
                    if not invite:
                        return self.reply(403, dict(error='Convite inválido, expirado ou já utilizado.'))
                    name, email = invite['name'], invite['email']
                    role = 'operador'
                    c.execute('UPDATE invitations SET used=1 WHERE token=?', (invite['token'],))
                c.execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)', (name, email, hashed, role))
                user = c.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
                auth.audit(c, user, 'conta_ativada', dict(papel=role))
            if role == 'admin':
                (DB.parent / 'activation-code').unlink(missing_ok=True)
        with auth.connect(DB) as c:
            c.executemany('DELETE FROM auth_attempts WHERE identity=?', [(i,) for i in identities])
        return self.create_session(user)

    def do_PUT(self):
        if not self.same_origin():
            return
        user = self.authorize(mutate=True)
        if not user:
            return
        try:
            if self.path != '/api/state':
                return self.reply(404, dict(error='Não encontrado'))
            return self.write_state(user, self.body())
        except (ValueError, KeyError, TypeError):
            return self.reply(400, dict(error='Alteração inválida. Preserve os registros históricos e confira as quantidades.'))

    def write_state(self, user, data, restore=False):
        state = data['state']
        validate_state(state)
        if type(data.get('revision')) is not int:
            raise ValueError('Revisão inválida.')
        with auth.connect(DB) as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT revision,payload FROM state WHERE id=1').fetchone()
            if old['revision'] != data['revision']:
                return self.reply(409, dict(error='Os dados foram alterados em outra sessão. Recarregue antes de continuar.'))
            details = annotate(json.loads(old['payload']), state, user, restore)
            payload = json.dumps(state, allow_nan=False)
            c.execute('UPDATE state SET revision=revision+1,payload=? WHERE id=1', (payload,))
            auth.audit(c, user, 'backup_restaurado' if restore else 'dados_atualizados', dict(revisao=old['revision'] + 1, alteracoes=details))
        return self.reply(200, dict(revision=old['revision'] + 1, state=state))

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'setup-code':
        file = DB.parent / 'activation-code'
        if file.exists():
            print(file.read_text())
        else:
            print('Administrador já ativado. Entre pela tela de login.')
        sys.exit(0)
    port = int(os.environ.get('CONTROLAI_PORT', '8081'))
    print(f'ControlAI: servidor local autenticado na porta {port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
