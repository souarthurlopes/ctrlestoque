"""Autenticação local: hashes de senha, sessões e convites com validade."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time

SESSION_SECONDS = 12 * 60 * 60

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def password_hash(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError('Use uma senha com 12 a 128 caracteres.')
    salt = secrets.token_hex(16)
    result = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + result

def password_check(password, encoded):
    if not isinstance(password, str) or len(password) > 128:
        return False
    salt, expected = encoded.split(':')
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(actual, expected)

def public_user(row):
    return dict(id=row['id'], nome=row['name'], email=row['email'], papel=row['role'])

def connect(db):
    c = sqlite3.connect(db, timeout=15)
    c.row_factory = sqlite3.Row
    return c

def initialize(db):
    with connect(db) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','operador')), active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, csrf TEXT NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS invitations(token TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, expires INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS auth_attempts(identity TEXT NOT NULL, at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at INTEGER NOT NULL, user_id INTEGER, actor TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL);
        ''')
        if not c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            # Código fora da pasta pública, nunca incluído no HTML ou nos logs.
            file = db.parent / 'activation-code'
            if not c.execute("SELECT 1 FROM settings WHERE key='activation'").fetchone():
                token = secrets.token_urlsafe(32)
                fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, 'w') as f:
                    f.write(token)
                c.execute("INSERT INTO settings VALUES ('activation',?)", (digest(token),))

def audit(c, user, action, details):
    c.execute('INSERT INTO audit(at,user_id,actor,action,details) VALUES(?,?,?,?,?)',
              (int(time.time()), user['id'] if user else None, user['name'] if user else 'Ativação', action, json.dumps(details, ensure_ascii=False)))

def identity(name, email):
    if not isinstance(name, str) or not name.strip() or len(name) > 150:
        raise ValueError('Informe um nome válido.')
    if not isinstance(email, str) or len(email) > 254 or '@' not in email or '.' not in email.rsplit('@', 1)[-1] or any(ch.isspace() for ch in email):
        raise ValueError('Informe um e-mail válido.')
    return name.strip(), email.strip().lower()
