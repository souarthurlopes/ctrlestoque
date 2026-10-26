#!/usr/bin/env python3
"""Backup criptografado. Credenciais somente em variáveis de ambiente."""
import datetime as dt
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

class BackupError(Exception):
    pass

def connection_environment(source):
    try:
        url = urlsplit(source.get('SUPABASE_DB_URL', ''))
        port = url.port or 5432
        if url.scheme not in ('postgres', 'postgresql') or not url.hostname or not url.username or not url.password or not url.path.strip('/'):
            raise ValueError()
    except ValueError:
        raise BackupError('Configure SUPABASE_DB_URL com a conexão PostgreSQL, não a URL da API REST.') from None
    # Não aceitar parâmetros que desabilitem verificação ou executem opções extras.
    result = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
    result.update(PGHOST=url.hostname, PGPORT=str(port), PGUSER=unquote(url.username), PGPASSWORD=unquote(url.password), PGDATABASE=unquote(url.path.lstrip('/')), PGSSLMODE='verify-full', PGCONNECT_TIMEOUT='30', PGAPPNAME='controlai-backup')
    return result

def command(args, env=None):
    try:
        result = subprocess.run(args, env=env, capture_output=True, timeout=900, check=True)
        return result.stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # Erros do cliente podem incluir dados da conexão. Não os imprimir.
        raise BackupError(f'{Path(args[0]).name} falhou. Verifique a configuração segura, certificados e permissões. Nenhum backup será publicado.') from None

def backup(destination):
    env = connection_environment(os.environ)
    public_key = os.environ.get('BACKUP_PUBLIC_KEY', '')
    fingerprint = re.sub(r'\s+', '', os.environ.get('BACKUP_KEY_FINGERPRINT', '')).upper()
    if not public_key.startswith('-----BEGIN PGP PUBLIC KEY BLOCK-----') or not re.fullmatch(r'[0-9A-F]{40}|[0-9A-F]{64}', fingerprint):
        raise BackupError('Configure BACKUP_PUBLIC_KEY e BACKUP_KEY_FINGERPRINT. Nunca forneça a chave privada ao agendamento.')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='controlai-backup-') as work:
        work = Path(work)
        home = work / 'gpg'
        home.mkdir(mode=0o700)
        env['GNUPGHOME'] = str(home)
        certificate = os.environ.get('SUPABASE_DB_CA_CERT', '')
        if certificate:
            cert = work / 'database-ca.pem'
            cert.write_text(certificate)
        else:
            cert = Path('/etc/ssl/certs/ca-certificates.crt')
        if not cert.is_file():
            raise BackupError('Configure o certificado CA do banco para verificar a conexão TLS.')
        env['PGSSLROOTCERT'] = str(cert)
        keyfile = work / 'recipient.asc'
        keyfile.write_text(public_key)
        metadata = command(['gpg', '--batch', '--with-colons', '--import-options', 'show-only', '--import', str(keyfile)], env).decode()
        if sum(line.startswith('pub:') for line in metadata.splitlines()) != 1:
            raise BackupError('Forneça uma única chave pública de destinatário.')
        first_fingerprint = next((line.split(':')[9] for line in metadata.splitlines() if line.startswith('fpr:')), '')
        if first_fingerprint != fingerprint:
            raise BackupError('A impressão digital não corresponde à chave pública configurada.')
        command(['gpg', '--batch', '--import', str(keyfile)], env)
        dump = work / 'database.dump'
        command(['pg_dump', '--format=custom', '--no-owner', '--no-acl', '--file', str(dump)], env)
        if not dump.is_file() or dump.stat().st_size == 0:
            raise BackupError('O banco não produziu um arquivo de backup válido.')
        command(['pg_restore', '--list', str(dump)], env)
        name = 'controlai-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.dump.gpg'
        # O arquivo em claro nunca entra no diretório publicado.
        encrypted = work / name
        command(['gpg', '--batch', '--yes', '--trust-model', 'always', '--recipient', fingerprint, '--output', str(encrypted), '--encrypt', str(dump)], env)
        target = destination / name
        partial = destination / (name + ".partial")
        try:
            shutil.copyfile(encrypted, partial)
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
        checksum = hashlib.sha256(target.read_bytes()).hexdigest()
        target.with_suffix(target.suffix + '.sha256').write_text(checksum + '  ' + name + '\n')
        print('Backup criptografado preparado:', target.name)
        return target

if __name__ == '__main__':
    try:
        backup(sys.argv[1] if len(sys.argv) > 1 else 'backups')
    except BackupError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
