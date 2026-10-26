import http.client
import json
import threading
import unittest
from unittest.mock import patch
import urllib.error
from supabase_server import Handler, RemoteError, Supabase
from http.server import ThreadingHTTPServer

class FakeSupabase:
    def __init__(self):
        self.calls = []
        self.fail = False

    def request(self, path, data=None, token=None):
        self.calls.append((path,data,token))
        if self.fail:
            raise RemoteError(503,'Conexão indisponível. Nenhum dado foi salvo localmente.')
        if path.startswith('/auth/v1/token'):
            return dict(access_token='test-admin-access',refresh_token='test-refresh',expires_in=3600)
        return {}

    def rpc(self, name, token, **parameters):
        self.calls.append((name,parameters,token))
        if self.fail:
            raise RemoteError(503,'Conexão indisponível. Nenhum dado foi salvo localmente.')
        if name == 'controlai_me':
            return dict(id='test-user',nome='Teste',email='test@example.test',papel='operador' if token=='test-operator' else 'admin')
        if name == 'controlai_read_state':
            return dict(revision=1,state=dict(estoque=[],obras=[],itens=[]))
        if name == 'controlai_write_state':
            return dict(revision=parameters['p_revision']+1,state=parameters['p_state'])
        if name == 'controlai_manage_user':
            return dict(ok=True,mode='supabase',message='Acesso autorizado; crie a conta no painel.')
        return {}

class SupabaseBridge(unittest.TestCase):
    def setUp(self):
        self.remote = FakeSupabase()
        class TestHandler(Handler):
            backend = self.remote
            def log_message(self,*args): pass
        self.server = ThreadingHTTPServer(('127.0.0.1',0),TestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,path,method='GET',data=None,token=None,csrf=True,origin=True):
        conn = http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        headers = {'Content-Type':'application/json'}
        if origin: headers['Origin']=f'http://127.0.0.1:{self.port}'
        if token:
            headers['Cookie']=f'ca_access={token}; ca_csrf=test-csrf'
            if csrf: headers['X-CSRF-Token']='test-csrf'
        conn.request(method,path,json.dumps(data) if data is not None else None,headers)
        res = conn.getresponse();body=json.loads(res.read());cookies=res.getheaders();code=res.status;conn.close()
        return code,body,cookies

    def test_login_keeps_tokens_out_of_json(self):
        code,data,headers=self.request('/api/auth/login','POST',dict(email='test@example.test',senha='test-password'))
        self.assertEqual(code,200)
        self.assertNotIn('access_token',data);self.assertNotIn('refresh_token',data)
        cookies=[v for k,v in headers if k.lower()=='set-cookie']
        self.assertEqual(len(cookies),3)
        self.assertTrue(all('HttpOnly' in v and 'SameSite=Strict' in v for v in cookies))
        self.assertEqual(data['provider'],'supabase')

    def test_write_requires_session_csrf_and_origin(self):
        payload=dict(revision=1,state=dict(estoque=[],obras=[],itens=[]))
        self.assertEqual(self.request('/api/state','PUT',payload)[0],403)
        self.assertEqual(self.request('/api/state','PUT',payload,token='test-admin',csrf=False)[0],403)
        self.assertEqual(self.request('/api/state','PUT',payload,token='test-admin',origin=False)[0],403)
        self.assertEqual(self.request('/api/state','PUT',payload,token='test-operator')[0],200)
        self.assertEqual(self.remote.calls[-1][0],'controlai_write_state')
        self.assertFalse(self.remote.calls[-1][1]['p_restore'])

    def test_admin_also_operates_but_operators_cannot_administer(self):
        for path in ('/api/users','/api/audit','/api/backup'):
            self.assertEqual(self.request(path,token='test-operator')[0],403)
        self.assertEqual(self.request('/api/restore','POST',dict(revision=1,state={}),token='test-operator')[0],403)
        self.assertEqual(self.request('/api/invitations','POST',{},token='test-operator')[0],403)
        self.assertEqual(self.request('/api/state',token='test-admin')[0],200)
        self.assertEqual(self.request('/api/invitations','POST',dict(nome='Apoio',email='apoio@example.test'),token='test-admin')[0],200)

    def test_no_sqlite_fallback_on_remote_failure(self):
        self.remote.fail=True
        code,data,_=self.request('/api/state',token='test-admin')
        self.assertEqual(code,503)
        self.assertIn('Nenhum dado foi salvo localmente',data['error'])
        self.assertEqual(self.request('/supabase/config.json')[0],404)
        self.assertEqual(self.request('/sqlite_server.py')[0],404)
        self.assertEqual(self.request('/api/state')[0],401)

class Transport(unittest.TestCase):
    def test_transport_uses_public_key_and_user_token(self):
        client=Supabase(dict(url='https://testproject.supabase.co',publishable_key='sb_publishable_test'))
        with patch('urllib.request.urlopen') as open_url:
            open_url.return_value.__enter__.return_value.read.return_value=b'{"ok":true}'
            self.assertTrue(client.rpc('controlai_me','test-token')['ok'])
            req=open_url.call_args.args[0]
            self.assertEqual(req.headers['Apikey'],'sb_publishable_test')
            self.assertEqual(req.headers['Authorization'],'Bearer test-token')
            self.assertTrue(req.full_url.startswith('https://'))
        with self.assertRaises(ValueError):
            Supabase(dict(url='http://testproject.supabase.co',publishable_key='sb_publishable_test'))
        with self.assertRaises(ValueError):
            Supabase(dict(url='https://testproject.supabase.co',publishable_key='service-role-is-not-allowed'))

if __name__=='__main__': unittest.main()
