import http.client
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]

class LoginFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.temp.name) / 'data.sqlite3'
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            cls.port = s.getsockname()[1]
        cls.origin = f'http://127.0.0.1:{cls.port}'
        cls.process = subprocess.Popen([sys.executable, 'server.py'], cwd=ROOT, env={**os.environ, 'CONTROLAI_BACKEND':'sqlite', 'CONTROLAI_DB':str(cls.db), 'CONTROLAI_PORT':str(cls.port)}, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cls.process.stdout.readline()

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.process.stdout.close()
        cls.temp.cleanup()

    def request(self, method, path, data=None, session=None, csrf=True, origin=True):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        headers = {'Content-Type':'application/json'}
        if origin:
            headers['Origin'] = self.origin
        if session:
            headers['Cookie'] = session['cookie']
            if csrf:
                headers['X-CSRF-Token'] = session['csrf']
        conn.request(method, path, json.dumps(data) if data is not None else None, headers)
        response = conn.getresponse()
        raw = response.read()
        cookie = response.getheader('Set-Cookie')
        status = response.status
        conn.close()
        return status, json.loads(raw), cookie

    def test_complete_flow(self):
        self.assertEqual(self.request('GET','/api/state')[0],401)
        self.assertEqual(self.request('GET','/api/audit')[0],401)
        code = (Path(self.temp.name) / 'activation-code').read_text()
        credentials = dict(nome='Administrador Teste', email='admin@example.test', senha='a-test-password-1234', codigo=code)
        status, admin, cookie = self.request('POST','/api/auth/setup',credentials)
        self.assertEqual(status,200)
        self.assertIn('HttpOnly',cookie)
        self.assertIn('SameSite=Strict',cookie)
        admin['cookie'] = cookie.split(';')[0]
        self.assertEqual(admin['user']['papel'],'admin')
        self.assertFalse((Path(self.temp.name) / 'activation-code').exists())
        self.assertEqual(self.request('POST','/api/auth/setup',credentials)[0],403)
        self.assertEqual(self.request('PUT','/api/state',{},admin,csrf=False)[0],403)
        self.assertEqual(self.request('POST','/api/invitations',{},admin,origin=False)[0],403)
        status, invitation, _ = self.request('POST','/api/invitations',dict(nome='Operador Teste',email='operador@example.test'),admin)
        self.assertEqual(status,201)
        status, operator, cookie = self.request('POST','/api/auth/accept',dict(token=invitation['token'],senha='another-test-password',papel='admin'))
        self.assertEqual(status,200)
        operator['cookie'] = cookie.split(';')[0]
        self.assertEqual(operator['user']['papel'],'operador')
        self.assertEqual(self.request('POST','/api/auth/accept',dict(token=invitation['token'],senha='another-test-password'))[0],403)
        for path in ('/api/users','/api/audit','/api/backup'):
            self.assertEqual(self.request('GET',path,session=operator)[0],403)
        self.assertEqual(self.request('POST','/api/restore',dict(state={},revision=0),operator)[0],403)
        self.assertEqual(self.request('POST','/api/invitations',dict(nome='Escalada',email='x@example.test'),operator)[0],403)
        _, current, _ = self.request('GET','/api/state',session=operator)
        state = current['state']
        state['estoque'] = [dict(codigo=1,cod_fab='ARNU09GM1A4',produto='Evaporadora',tipo='Evaporadora',saldo=10)]
        state['obras'] = [dict(id=1,nome='Obra A',end='Rua A')]
        state['pedidos'] = [dict(id='p1',obraId=1,obraNome='Obra A',numero='PED-0001',linhas=[dict(id='l1',qtd=5,modelo='ARNU09GM1A4')],criadoPor=dict(id=999,nome='Falso'))]
        status, saved, _ = self.request('PUT','/api/state',dict(state=state,revision=current['revision']),operator)
        self.assertEqual(status,200)
        self.assertEqual(saved['state']['pedidos'][0]['criadoPor']['nome'],'Operador Teste')
        self.assertEqual(self.request('PUT','/api/state',dict(state=state,revision=current['revision']),operator)[0],409)
        state = saved['state']
        state['entregas'] = [dict(id='e1',pedidoId='p1',linhaId='l1',qtd=2,modelo='ARNU09GM1A4')]
        status, saved, _ = self.request('PUT','/api/state',dict(state=state,revision=saved['revision']),admin)
        self.assertEqual(status,200)
        self.assertEqual(saved['state']['entregas'][0]['criadoPor']['nome'],'Administrador Teste')
        self.assertEqual(saved['state']['estoque'][0]['saldo'],10)
        revision = saved['revision']
        state = saved['state']
        state['entregas'][0]['qtd'] = 3
        self.assertEqual(self.request('PUT','/api/state',dict(state=state,revision=revision),admin)[0],400)
        state['entregas'] = []
        self.assertEqual(self.request('PUT','/api/state',dict(state=state,revision=revision),operator)[0],400)
        _, saved, _ = self.request('GET','/api/state',session=admin)
        state = saved['state']
        state['entregas'].append(dict(id='e2',pedidoId='p1',linhaId='l1',qtd=4))
        self.assertEqual(self.request('PUT','/api/state',dict(state=state,revision=revision),operator)[0],400)
        # Administrador também opera: cadastro de outra obra permitido.
        _, saved, _ = self.request('GET','/api/state',session=admin)
        saved['state']['obras'].append(dict(id=2,nome='Obra B'))
        status, saved, _ = self.request('PUT','/api/state',saved,admin)
        self.assertEqual(status,200)
        _, logs, _ = self.request('GET','/api/audit',session=admin)
        self.assertIn('Operador Teste',[r['usuario'] for r in logs['registros']])
        # Limite de três contas, incluindo convites ainda não usados.
        self.assertEqual(self.request('POST','/api/invitations',dict(nome='Segundo',email='segundo@example.test'),admin)[0],201)
        self.assertEqual(self.request('POST','/api/invitations',dict(nome='Quarto',email='quarto@example.test'),admin)[0],400)
        self.assertEqual(self.request('POST','/api/users/active',dict(id=operator['user']['id'],ativo=False),admin)[0],200)
        self.assertEqual(self.request('GET','/api/state',session=operator)[0],401)
        self.assertEqual(self.request('POST','/api/auth/login',dict(email='operador@example.test',senha='another-test-password'))[0],401)
        self.assertEqual(self.request('GET','/auth.py')[0],404)
        # Senhas e tokens não são persistidos em texto puro.
        with sqlite3.connect(self.db) as c:
            hashed = c.execute('SELECT password FROM users WHERE role="admin"').fetchone()[0]
            self.assertNotEqual(hashed,credentials['senha'])
            self.assertNotEqual(c.execute('SELECT token FROM sessions LIMIT 1').fetchone()[0],admin['cookie'].split('=',1)[1])
        self.assertEqual(self.request('POST','/api/auth/logout',{},admin)[0],200)
        self.assertEqual(self.request('GET','/api/state',session=admin)[0],401)
        self.assertEqual(self.request('POST','/api/auth/login',dict(email=credentials['email'],senha='wrong'))[0],401)
        self.assertEqual(self.request('POST','/api/auth/login',credentials)[0],200)

if __name__ == '__main__':
    unittest.main()
