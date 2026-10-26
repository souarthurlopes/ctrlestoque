import io
import json
import unittest
from wsgiref.util import setup_testing_defaults
from wsgiref.validate import validator
from wsgi import create_app
from test_supabase import FakeSupabase

class ProductionEntry(unittest.TestCase):
    def request(self,path,method='GET',data=None,token=None):
        env={};setup_testing_defaults(env)
        env.update(QUERY_STRING='',PATH_INFO=path,REQUEST_METHOD=method,HTTP_HOST='controlai.example',HTTP_ORIGIN='https://controlai.example',SERVER_NAME='controlai.example',SERVER_PORT='443')
        env['wsgi.url_scheme']='https'
        payload=json.dumps(data).encode() if data is not None else b''
        env.update(CONTENT_LENGTH=str(len(payload)),CONTENT_TYPE='application/json')
        env['wsgi.input']=io.BytesIO(payload)
        if token:
            env.update(HTTP_COOKIE=f'ca_access={token}; ca_csrf=test-csrf',HTTP_X_CSRF_TOKEN='test-csrf')
        result={}
        def start(status,headers,exc_info=None):
            result.update(status=status,headers=headers)
            return lambda data:None
        app=validator(create_app(FakeSupabase(),secure_cookie=True))
        stream=app(env,start)
        try: result['body']=b''.join(stream)
        finally: stream.close()
        return result

    def test_application_assets_and_health(self):
        page=self.request('/')
        self.assertTrue(page['status'].startswith('200'))
        self.assertIn(b'ControlAI',page['body'])
        self.assertTrue(self.request('/auth.js')['status'].startswith('200'))
        health=self.request('/healthz')
        self.assertEqual(json.loads(health['body']),dict(status='ok',backend='supabase'))
        self.assertTrue(self.request('/supabase/config.json')['status'].startswith('404'))
        self.assertEqual(self.request('/sqlite_server.py','HEAD')['body'],b'')
        self.assertTrue(self.request('/sqlite_server.py','HEAD')['status'].startswith('404'))

    def test_cookies_and_authenticated_operations(self):
        result=self.request('/api/auth/login','POST',dict(email='test@example.test',senha='test-password'))
        self.assertTrue(result['status'].startswith('200'))
        cookies=[v for k,v in result['headers'] if k=='Set-Cookie']
        self.assertEqual(len(cookies),3)
        self.assertTrue(all('; Secure' in v and 'HttpOnly' in v for v in cookies))
        data=json.loads(result['body']);self.assertNotIn('access_token',data)
        self.assertTrue(self.request('/api/state')['status'].startswith('401'))
        write=self.request('/api/state','PUT',dict(revision=1,state={}),token='test-operator')
        self.assertTrue(write['status'].startswith('200'))
        self.assertTrue(self.request('/api/users',token='test-operator')['status'].startswith('403'))
        headers=dict(write['headers'])
        self.assertEqual(headers['X-Frame-Options'],'DENY')
        self.assertEqual(headers['Cache-Control'],'no-store')

if __name__=='__main__': unittest.main()
