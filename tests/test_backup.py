import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('backup', Path(__file__).resolve().parents[1] / 'scripts' / 'backup_supabase.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)

class BackupChecks(unittest.TestCase):
    def test_database_connection_enforces_tls(self):
        with patch.dict(os.environ, {'PGSSLMODE':'disable'}):
            env = backup.connection_environment({'SUPABASE_DB_URL':'postgresql://postgres.test:example%40password@pooler.example.test:5432/postgres?sslmode=disable'})
        self.assertEqual(env['PGSSLMODE'], 'verify-full')
        self.assertEqual(env['PGPASSWORD'], 'example@password')
        self.assertEqual(env['PGHOST'], 'pooler.example.test')
        self.assertEqual(env['PGPORT'], '5432')

    def test_rest_url_not_a_database_connection(self):
        with self.assertRaises(backup.BackupError):
            backup.connection_environment({'SUPABASE_DB_URL':'https://uyeopkssqzxjaooqjehl.supabase.co/rest/v1/'})

    def test_command_failure_does_not_reveal_credentials(self):
        secret = 'only-a-test-credential'
        with patch.object(subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'pg_dump', stderr=secret.encode())):
            with self.assertRaises(backup.BackupError) as error:
                backup.command(['pg_dump'])
        self.assertNotIn(secret, str(error.exception))

    @unittest.skipUnless(shutil.which('gpg'), 'GnuPG necessário para o teste de criptografia')
    def test_real_encryption_and_decryption_with_synthetic_database(self):
        # Chave descartável de teste. Nenhuma conta ou conexão real é usada.
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            home = root / 'key'; home.mkdir(mode=0o700)
            env = {**os.environ, 'GNUPGHOME':str(home)}
            def gpg(*args):
                return subprocess.run(['gpg', '--batch', *args], env=env, capture_output=True, check=True).stdout
            gpg('--pinentry-mode','loopback','--passphrase','','--quick-generate-key','Synthetic Backup Test <test@example.test>','rsa2048','encr','1d')
            fingerprint = next(l.split(':')[9] for l in gpg('--with-colons','--list-keys').decode().splitlines() if l.startswith('fpr:'))
            public = gpg('--armor','--export',fingerprint).decode()
            original = backup.command
            payload = b'SYNTHETIC DATABASE CONTENT - NOT REAL DATA'
            def command(args, env=None):
                if args[0] == 'pg_dump':
                    self.assertEqual(env['PGSSLMODE'],'verify-full')
                    Path(args[args.index('--file')+1]).write_bytes(payload)
                    return b''
                if args[0] == 'pg_restore':
                    return b'Synthetic format check; real pg_restore not exercised.'
                return original(args, env)
            variables = {'SUPABASE_DB_URL':'postgresql://example:test-password@database.example.test/postgres','BACKUP_PUBLIC_KEY':public,'BACKUP_KEY_FINGERPRINT':fingerprint}
            with patch.dict(os.environ, variables), patch.object(backup,'command',side_effect=command):
                target = backup.backup(root/'output')
            self.assertNotIn(payload,target.read_bytes())
            self.assertEqual(gpg('--decrypt',str(target)),payload)
            self.assertEqual(sorted(p.suffix for p in (root/'output').iterdir()),['.gpg','.sha256'])
            variables['BACKUP_KEY_FINGERPRINT'] = '0'*40
            with patch.dict(os.environ,variables), self.assertRaises(backup.BackupError):
                backup.backup(root/'mismatch')
            self.assertEqual(list((root/'mismatch').iterdir()),[])

if __name__ == '__main__':
    unittest.main()
