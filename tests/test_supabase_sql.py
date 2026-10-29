"""Integração SQL em PostgreSQL descartável. Não usa o projeto real."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import unittest

@unittest.skipUnless(os.environ.get('RUN_POSTGRES_TESTS')=='1' and shutil.which('docker'), 'Defina RUN_POSTGRES_TESTS=1 para PostgreSQL via Docker')
class SupabaseSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run=subprocess.run(['docker','run','--detach','--rm','--network','none','--env','POSTGRES_HOST_AUTH_METHOD=trust','postgres:18-alpine','-c','listen_addresses='],capture_output=True,text=True,check=True)
        cls.container=run.stdout.strip()
        cls.addClassCleanup(lambda: subprocess.run(['docker','rm','--force',cls.container],capture_output=True))
        for _ in range(60):
            logs=subprocess.run(['docker','logs',cls.container],capture_output=True,text=True)
            initialized='PostgreSQL init process complete' in (logs.stdout+logs.stderr)
            if initialized and subprocess.run(['docker','exec',cls.container,'pg_isready','-U','postgres'],capture_output=True).returncode==0: break
            time.sleep(.2)
        else: raise RuntimeError('PostgreSQL temporário não iniciou.')
        cls.sql('''create role anon; create role authenticated;
        create schema auth;
        create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);
        create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
        ''')
        migration=(Path(__file__).resolve().parents[1]/'supabase/setup.sql').read_text()
        cls.sql(migration)
        cls.sql(migration) # Reaplicação preserva as tabelas e continua válida.
        cls.sql("""update public.controlai_members set email='admin@example.test',name='Admin Test' where role='admin';
        insert into auth.users values
        ('00000000-0000-0000-0000-000000000001','admin@example.test',now()),
        ('00000000-0000-0000-0000-000000000002','operator@example.test',now()),
        ('00000000-0000-0000-0000-000000000003','other@example.test',now()),
        ('00000000-0000-0000-0000-000000000004','unconfirmed@example.test',null);
        """)

    @classmethod
    def sql(cls, statement, user=None, failure=False, role=None):
        if user:
            statement=f"begin; set local role authenticated; set local request.jwt.claim.sub='00000000-0000-0000-0000-{user:012d}'; "+statement+'; commit;'
        elif role:
            statement=f'begin; set local role {role}; '+statement+'; commit;'
        r=subprocess.run(['docker','exec','-i',cls.container,'psql','-U','postgres','-v','ON_ERROR_STOP=1','-t','-A','-q'],input=statement,capture_output=True,text=True)
        if failure:
            if r.returncode==0: raise AssertionError('A operação proibida passou: '+statement)
            return r.stderr
        if r.returncode: raise AssertionError(r.stderr)
        return r.stdout.strip()

    def call(self, function, args='',user=1,failure=False):
        raw=self.sql('select public.'+function+'('+args+')',user=user,failure=failure)
        return raw if failure else json.loads(raw)

    def save(self,state,revision,user=1,restore=False,failure=False):
        data=json.dumps(state).replace("'","''")
        return self.call('controlai_write_state',f"{revision},'{data}'::jsonb,{str(restore).lower()}",user=user,failure=failure)

    def test_create_work_with_legacy_counter(self):
        current=self.call('controlai_read_state')
        state=current['state']
        state['obras']=[dict(id=1,nome='Obra existente')]
        state['nid']=1 # Contador legado desatualizado.
        current=self.save(state,current['revision'])
        duplicate=json.loads(json.dumps(current['state']))
        duplicate['obras'].append(dict(id=1,nome='Nova obra'))
        self.assertIn('Identificador duplicado',self.save(duplicate,current['revision'],failure=True))
        corrected=json.loads(json.dumps(current['state']))
        corrected['obras'].append(dict(id=2,nome='Nova obra'))
        corrected['nid']=3
        saved=self.save(corrected,current['revision'])
        self.assertEqual([o['nome'] for o in saved['state']['obras']],['Obra existente','Nova obra'])
        self.assertEqual(saved['state']['pedidos'],current['state']['pedidos'])
        diagnostic=self.sql((Path(__file__).resolve().parents[1]/'supabase/diagnostico-obras.sql').read_text())
        self.assertEqual(diagnostic.split('|'),['3','2','0','t','t','f'])
        self.assertEqual(self.call('controlai_read_state')['revision'],saved['revision'])

    def test_policies_roles_history_and_quantities(self):
        self.sql('select public.controlai_me()',role='anon',failure=True)
        self.sql('select * from public.controlai_state',user=1,failure=True)
        self.call('controlai_me',user=3,failure=True)
        self.call('controlai_me',user=4,failure=True)
        self.assertEqual(self.call('controlai_me')['papel'],'admin')
        self.call('controlai_manage_user',"'operator@example.test','Operator Test',true")
        self.call('controlai_manage_user',"'other@example.test','Other Test',true")
        self.call('controlai_manage_user',"'fourth@example.test','Fourth Test',true",failure=True)
        self.call('controlai_manage_user',"'fifth@example.test','Escalation',true",user=2,failure=True)
        self.call('controlai_get_audit',user=2,failure=True)
        self.call('controlai_read_state','true',user=2,failure=True)
        s=self.call('controlai_read_state',user=2)
        s['state']['obras']=[dict(id=1,nome='Obra Teste')]
        s['state']['estoque']=[dict(codigo=1,cod_fab='ARNU09GM1A4',tipo='Evaporadora',saldo=10)]
        s['state']['pedidos']=[dict(id='p1',obraId=1,numero='PED-0001',linhas=[dict(id='l1',qtd=5)],criadoPor=dict(nome='Forged'))]
        s=self.save(s['state'],s['revision'],user=2)
        self.assertEqual(s['state']['pedidos'][0]['criadoPor']['nome'],'Operator Test')
        self.save(s['state'],s['revision']-1,user=2,failure=True)
        s['state']['entregas']=[dict(id='e1',pedidoId='p1',linhaId='l1',qtd=2)]
        s=self.save(s['state'],s['revision'],user=1)
        self.assertEqual(s['state']['entregas'][0]['criadoPor']['nome'],'Admin Test')
        self.assertEqual(s['state']['estoque'][0]['saldo'],10)
        # Edição de cadastro mantém ID, pedidos e entregas históricos.
        pedidos_antes=json.loads(json.dumps(s['state']['pedidos']))
        entregas_antes=json.loads(json.dumps(s['state']['entregas']))
        s['state']['obras'][0].update(nome='Obra revisada',end='Novo endereço',resp='Novo responsável')
        s=self.save(s['state'],s['revision'],user=2)
        self.assertEqual(s['state']['obras'][0]['id'],1)
        self.assertEqual(s['state']['pedidos'],pedidos_antes)
        self.assertEqual(s['state']['entregas'],entregas_antes)
        bad=json.loads(json.dumps(s['state']));bad['entregas'][0]['qtd']=3
        self.save(bad,s['revision'],failure=True)
        bad=json.loads(json.dumps(s['state']));bad['entregas']=[]
        self.save(bad,s['revision'],user=2,failure=True)
        self.save(bad,s['revision'],user=2,restore=True,failure=True)
        bad=json.loads(json.dumps(s['state']));bad['entregas'].append(dict(id='e2',pedidoId='p1',linhaId='l1',qtd=4))
        self.save(bad,s['revision'],failure=True)
        # Cliente não consegue falsificar a autoria de uma entrega existente.
        s['state']['entregas'][0]['criadoPor']=dict(nome='Forged')
        s=self.save(s['state'],s['revision'])
        self.assertEqual(s['state']['entregas'][0]['criadoPor']['nome'],'Admin Test')
        before=self.call('controlai_get_audit')['registros']
        s['state']['entregas']=[]
        s=self.save(s['state'],s['revision'],restore=True)
        after=self.call('controlai_get_audit')['registros']
        self.assertGreater(len(after),len(before))
        self.assertEqual(after[0]['acao'],'backup_restaurado')
        self.call('controlai_manage_user',"'operator@example.test',null,false")
        self.call('controlai_read_state',user=2,failure=True)

if __name__=='__main__': unittest.main()
