import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
import uuid

_VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vendor')
if os.path.isdir(_VENDOR) and _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

import pymysql

EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]{2,}$')
SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 64 * 1024 * 1024
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
REMEMBER_TTL = 30 * 24 * 60 * 60
TAB_TTL = 24 * 60 * 60
MAX_ATTEMPTS = 5
LOCK_STEPS = [60, 300, 900, 1800]
COLORS = ['#3ef2b5', '#5fc6ff', '#b98bff', '#ffc857', '#ff8fd8', '#a8ff60', '#ff8a1e']
MAX_AVATAR_CHARS = 2_500_000

_SCHEMA_READY = False
_DUMMY_HASH = None


def now_seconds():
    return int(time.time())


def normalize_email(value):
    return str(value or '').strip().lower()


def b64url_encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def b64url_decode(value):
    text = str(value or '')
    return base64.urlsafe_b64decode(text + '=' * ((4 - len(text) % 4) % 4))


def sha256_hex(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def mask_email(value):
    return sha256_hex('orbita-email:' + normalize_email(value))


def db_config():
    keys = ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USERNAME', 'DB_PASSWORD']
    missing = [key for key in keys if not os.environ.get(key)]
    if missing:
        raise RuntimeError('database_not_configured')
    return {
        'host': os.environ['DB_HOST'],
        'port': int(os.environ['DB_PORT']),
        'user': os.environ['DB_USERNAME'],
        'password': os.environ['DB_PASSWORD'],
        'database': os.environ['DB_NAME'],
    }


def connect():
    config = db_config()
    return pymysql.connect(
        **config,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        ssl={'ssl_verify_cert': False, 'ssl_verify_identity': False},
        connect_timeout=15,
        read_timeout=20,
        write_timeout=20,
        autocommit=True,
    )


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS orbita_accounts (
      id CHAR(36) NOT NULL PRIMARY KEY,
      email VARCHAR(254) NOT NULL,
      name VARCHAR(60) NOT NULL,
      color CHAR(7) NOT NULL,
      avatar MEDIUMTEXT NULL,
      password_scheme VARCHAR(16) NOT NULL,
      password_salt VARCHAR(255) NOT NULL DEFAULT '',
      password_hash VARCHAR(512) NOT NULL,
      password_iterations INT NOT NULL DEFAULT 0,
      password_cost INT NOT NULL DEFAULT 0,
      password_score TINYINT NOT NULL DEFAULT 0,
      created_at BIGINT NOT NULL,
      last_login_at BIGINT NULL,
      password_changed_at BIGINT NULL,
      failed_attempts INT NOT NULL DEFAULT 0,
      lockouts INT NOT NULL DEFAULT 0,
      locked_until BIGINT NOT NULL DEFAULT 0,
      two_factor_enabled TINYINT(1) NOT NULL DEFAULT 0,
      two_factor_secret VARCHAR(255) NULL,
      two_factor_backup_codes MEDIUMTEXT NULL,
      source VARCHAR(16) NOT NULL DEFAULT 'web',
      source_id VARCHAR(64) NULL,
      updated_at BIGINT NOT NULL,
      UNIQUE KEY uq_orbita_accounts_email (email),
      UNIQUE KEY uq_orbita_accounts_source (source, source_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS orbita_sessions (
      token_hash CHAR(64) NOT NULL PRIMARY KEY,
      account_id CHAR(36) NOT NULL,
      created_at BIGINT NOT NULL,
      expires_at BIGINT NOT NULL,
      last_seen_at BIGINT NOT NULL,
      user_agent VARCHAR(255) NULL,
      ip_hash CHAR(64) NULL,
      KEY idx_orbita_sessions_account (account_id),
      KEY idx_orbita_sessions_expiry (expires_at),
      CONSTRAINT fk_orbita_sessions_account FOREIGN KEY (account_id)
        REFERENCES orbita_accounts (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS orbita_auth_events (
      id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
      account_id CHAR(36) NULL,
      kind VARCHAR(32) NOT NULL,
      detail VARCHAR(255) NULL,
      ip_hash CHAR(64) NULL,
      created_at BIGINT NOT NULL,
      KEY idx_orbita_events_account (account_id, created_at),
      KEY idx_orbita_events_kind (kind, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS orbita_imports (
      id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
      source VARCHAR(16) NOT NULL,
      source_id VARCHAR(64) NOT NULL,
      email_hash CHAR(64) NOT NULL,
      status VARCHAR(24) NOT NULL,
      detail VARCHAR(255) NULL,
      created_at BIGINT NOT NULL,
      UNIQUE KEY uq_orbita_imports_source (source, source_id),
      KEY idx_orbita_imports_email (email_hash)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


def ensure_schema(conn):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with conn.cursor() as cur:
        for statement in SCHEMA_STATEMENTS:
            cur.execute(statement)
    _SCHEMA_READY = True


def log_event(conn, kind, account_id=None, detail=None, ip_hash=None):
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO orbita_auth_events (account_id, kind, detail, ip_hash, created_at) VALUES (%s, %s, %s, %s, %s)',
            (account_id, kind[:32], (detail or '')[:255] or None, ip_hash, now_seconds()),
        )


def make_scrypt_hash(password):
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode('utf-8'),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=64,
        maxmem=SCRYPT_MAXMEM,
    )
    return f'scrypt${SCRYPT_N}${b64url_encode(salt)}${b64url_encode(derived)}'


def _dummy_scrypt_hash():
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = make_scrypt_hash(secrets.token_urlsafe(24))
    return _DUMMY_HASH


def verify_scrypt(password, stored):
    parts = str(stored or '').split('$')
    if len(parts) != 4 or parts[0] != 'scrypt':
        return False
    try:
        cost = int(parts[1])
        if cost < 2 or cost > 1_048_576:
            return False
        salt = b64url_decode(parts[2])
        expected = b64url_decode(parts[3])
        if len(salt) < 8 or not expected:
            return False
        derived = hashlib.scrypt(
            password.encode('utf-8'),
            salt=salt,
            n=cost,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=len(expected),
            maxmem=SCRYPT_MAXMEM,
        )
        return hmac.compare_digest(derived, expected)
    except (ValueError, IndexError, OSError):
        return False


def verify_pbkdf2(password, salt_b64, hash_b64, iterations):
    try:
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        rounds = int(iterations)
        if rounds < 100_000 or rounds > 2_000_000 or not salt or not expected:
            return False
        derived = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, rounds, dklen=len(expected))
        return hmac.compare_digest(derived, expected)
    except (ValueError, TypeError):
        return False


def verify_account_password(password, row):
    scheme = row.get('password_scheme')
    if scheme == 'scrypt':
        return verify_scrypt(password, row.get('password_hash'))
    if scheme == 'pbkdf2':
        return verify_pbkdf2(
            password,
            row.get('password_salt'),
            row.get('password_hash'),
            row.get('password_iterations'),
        )
    return False


def public_account(row):
    return {
        'id': row['id'],
        'name': row['name'],
        'email': row['email'],
        'avatar': row.get('avatar') or None,
        'color': row.get('color') or '#3ef2b5',
        'createdAt': int(row.get('created_at') or 0),
        'lastLoginAt': int(row['last_login_at']) if row.get('last_login_at') else None,
    }


def find_by_email(conn, email):
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM orbita_accounts WHERE email = %s LIMIT 1', (email,))
        return cur.fetchone()


def find_by_session(conn, token):
    if not token or len(token) > 200:
        return None, None
    token_hash = sha256_hex(token)
    now = now_seconds()
    with conn.cursor() as cur:
        cur.execute(
            'SELECT * FROM orbita_sessions WHERE token_hash = %s AND expires_at > %s LIMIT 1',
            (token_hash, now),
        )
        session = cur.fetchone()
        if not session:
            cur.execute('DELETE FROM orbita_sessions WHERE token_hash = %s', (token_hash,))
            return None, None
        cur.execute(
            'UPDATE orbita_sessions SET last_seen_at = %s WHERE token_hash = %s',
            (now, token_hash),
        )
        cur.execute('SELECT * FROM orbita_accounts WHERE id = %s LIMIT 1', (session['account_id'],))
        account = cur.fetchone()
    return account, session


def create_session(conn, account, remember, user_agent=None, ip_hash=None):
    token = secrets.token_urlsafe(32)
    token_hash = sha256_hex(token)
    created = now_seconds()
    ttl = REMEMBER_TTL if remember else TAB_TTL
    expires_at = created + ttl
    with conn.cursor() as cur:
        cur.execute('DELETE FROM orbita_sessions WHERE expires_at <= %s', (created,))
        cur.execute(
            'INSERT INTO orbita_sessions (token_hash, account_id, created_at, expires_at, last_seen_at, user_agent, ip_hash) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (
                token_hash,
                account['id'],
                created,
                expires_at,
                created,
                (user_agent or '')[:255] or None,
                ip_hash,
            ),
        )
    return token, expires_at


def _register_failure(conn, account):
    now = now_seconds()
    attempts = int(account.get('failed_attempts') or 0) + 1
    lockouts = int(account.get('lockouts') or 0)
    locked_until = 0
    if attempts >= MAX_ATTEMPTS:
        step = min(lockouts, len(LOCK_STEPS) - 1)
        locked_until = now + LOCK_STEPS[step]
        lockouts += 1
        attempts = 0
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE orbita_accounts SET failed_attempts = %s, lockouts = %s, locked_until = %s, updated_at = %s WHERE id = %s',
            (attempts, lockouts, locked_until, now, account['id']),
        )
    return locked_until


def _clear_failures(conn, account):
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE orbita_accounts SET failed_attempts = 0, lockouts = 0, locked_until = 0 WHERE id = %s',
            (account['id'],),
        )


def login(conn, email, password, remember, user_agent=None, ip_hash=None):
    email = normalize_email(email)
    password = str(password or '')
    if not email or not password or len(password) > MAX_PASSWORD_LENGTH:
        return {'ok': False, 'code': 'invalid_credentials'}
    account = find_by_email(conn, email)
    if not account:
        verify_scrypt(password, _dummy_scrypt_hash())
        log_event(conn, 'login_failed', detail='unknown_email', ip_hash=ip_hash)
        return {'ok': False, 'code': 'invalid_credentials'}

    now = now_seconds()
    if int(account.get('locked_until') or 0) > now:
        retry_after = int(account['locked_until']) - now
        log_event(conn, 'login_locked', account['id'], ip_hash=ip_hash)
        return {'ok': False, 'code': 'locked', 'retryAfter': retry_after}

    if not verify_account_password(password, account):
        locked_until = _register_failure(conn, account)
        log_event(conn, 'login_failed', account['id'], detail='bad_password', ip_hash=ip_hash)
        if locked_until > now:
            return {'ok': False, 'code': 'locked', 'retryAfter': locked_until - now}
        return {'ok': False, 'code': 'invalid_credentials'}

    _clear_failures(conn, account)
    if int(account.get('two_factor_enabled') or 0):
        log_event(conn, 'login_2fa_blocked', account['id'], ip_hash=ip_hash)
        return {'ok': False, 'code': 'two_factor_unsupported'}

    with conn.cursor() as cur:
        cur.execute(
            'UPDATE orbita_accounts SET last_login_at = %s, updated_at = %s WHERE id = %s',
            (now, now, account['id']),
        )
    token, expires_at = create_session(conn, account, bool(remember), user_agent, ip_hash)
    account['last_login_at'] = now
    log_event(conn, 'login_ok', account['id'], ip_hash=ip_hash)
    return {'ok': True, 'account': public_account(account), 'expiresAt': expires_at, 'token': token}


def register(conn, name, email, password, remember, user_agent=None, ip_hash=None):
    name = str(name or '').strip()
    email = normalize_email(email)
    password = str(password or '')
    if len(name) < 2 or len(name) > 60:
        return {'ok': False, 'code': 'invalid_input'}
    if not EMAIL_RE.match(email) or len(email) > 254:
        return {'ok': False, 'code': 'invalid_input'}
    if len(password) < MIN_PASSWORD_LENGTH or len(password) > MAX_PASSWORD_LENGTH:
        return {'ok': False, 'code': 'invalid_input'}
    if find_by_email(conn, email):
        return {'ok': False, 'code': 'email_exists'}

    account_id = str(uuid.uuid4())
    created = now_seconds()
    row = {
        'id': account_id,
        'email': email,
        'name': name,
        'color': secrets.choice(COLORS),
        'avatar': None,
        'password_scheme': 'scrypt',
        'password_salt': '',
        'password_hash': make_scrypt_hash(password),
        'password_iterations': SCRYPT_N,
        'password_cost': SCRYPT_N,
        'password_score': 0,
        'created_at': created,
        'last_login_at': created,
        'password_changed_at': created,
        'two_factor_enabled': 0,
        'source': 'web',
        'source_id': None,
        'updated_at': created,
    }
    try:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO orbita_accounts (id, email, name, color, avatar, password_scheme, password_salt, password_hash, '
                'password_iterations, password_cost, password_score, created_at, last_login_at, password_changed_at, '
                'two_factor_enabled, source, source_id, updated_at) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (
                    row['id'], row['email'], row['name'], row['color'], row['avatar'], row['password_scheme'],
                    row['password_salt'], row['password_hash'], row['password_iterations'], row['password_cost'],
                    row['password_score'], row['created_at'], row['last_login_at'], row['password_changed_at'],
                    row['two_factor_enabled'], row['source'], row['source_id'], row['updated_at'],
                ),
            )
    except pymysql.err.IntegrityError:
        return {'ok': False, 'code': 'email_exists'}

    token, expires_at = create_session(conn, row, bool(remember), user_agent, ip_hash)
    log_event(conn, 'register_ok', account_id, ip_hash=ip_hash)
    return {'ok': True, 'account': public_account(row), 'expiresAt': expires_at, 'token': token}


def logout(conn, token):
    if token:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM orbita_sessions WHERE token_hash = %s', (sha256_hex(token),))


def update_profile(conn, account_id, avatar):
    if avatar is not None:
        avatar = str(avatar)
        if not avatar.startswith('data:image/') or len(avatar) > MAX_AVATAR_CHARS:
            return {'ok': False, 'code': 'invalid_avatar'}
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE orbita_accounts SET avatar = %s, updated_at = %s WHERE id = %s',
            (avatar, now_seconds(), account_id),
        )
        cur.execute('SELECT * FROM orbita_accounts WHERE id = %s LIMIT 1', (account_id,))
        row = cur.fetchone()
    return {'ok': True, 'account': public_account(row)} if row else {'ok': False, 'code': 'not_found'}


def _valid_avatar(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or not text.startswith('data:image/') or len(text) > MAX_AVATAR_CHARS:
        return None
    return text


def _valid_desktop_hash(value):
    parts = str(value or '').split('$')
    if len(parts) != 4 or parts[0] != 'scrypt':
        return False
    try:
        cost = int(parts[1])
        if cost < 2 or cost > 1_048_576:
            return False
        return bool(b64url_decode(parts[2])) and bool(b64url_decode(parts[3]))
    except (ValueError, IndexError):
        return False


def import_desktop_account(conn, account):
    source_id = str(account.get('id') or '').strip()[:64]
    email = normalize_email(account.get('email'))
    name = str(account.get('name') or '').strip()[:60]
    password_hash = str(account.get('passwordHash') or '')
    if not source_id or not EMAIL_RE.match(email) or len(email) > 254 or not name:
        return {'status': 'invalid'}
    if not _valid_desktop_hash(password_hash):
        return {'status': 'invalid'}
    now = now_seconds()
    avatar = _valid_avatar(account.get('avatar'))
    two_factor = account.get('twoFactor') if isinstance(account.get('twoFactor'), dict) else {}
    two_factor_enabled = 1 if two_factor.get('enabled') and two_factor.get('secret') else 0
    two_factor_secret = str(two_factor.get('secret') or '')[:255] or None if two_factor_enabled else None
    backup_codes = two_factor.get('backupCodes') if isinstance(two_factor.get('backupCodes'), list) else []
    backup_json = json.dumps([str(code) for code in backup_codes if isinstance(code, str)]) if two_factor_enabled else None
    created_at = int(account.get('createdAt') or now)
    last_login_at = int(account.get('lastLoginAt') or 0) or None
    password_changed_at = int(account.get('passwordChangedAt') or 0) or created_at

    existing = find_by_email(conn, email)
    status = 'inserted'
    if existing:
        if existing.get('source') == 'desktop' and existing.get('source_id') == source_id:
            with conn.cursor() as cur:
                cur.execute(
                    'UPDATE orbita_accounts SET name = %s, color = %s, avatar = %s, password_scheme = %s, '
                    'password_hash = %s, password_iterations = %s, password_cost = %s, created_at = %s, '
                    'last_login_at = %s, password_changed_at = %s, two_factor_enabled = %s, two_factor_secret = %s, '
                    'two_factor_backup_codes = %s, updated_at = %s WHERE id = %s',
                    (
                        name, str(account.get('color') or '#3ef2b5')[:7], avatar, 'scrypt', password_hash,
                        SCRYPT_N, SCRYPT_N, created_at, last_login_at, password_changed_at,
                        two_factor_enabled, two_factor_secret, backup_json, now, existing['id'],
                    ),
                )
            status = 'updated'
        else:
            status = 'conflict'
    else:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO orbita_accounts (id, email, name, color, avatar, password_scheme, password_salt, password_hash, '
                'password_iterations, password_cost, password_score, created_at, last_login_at, password_changed_at, '
                'two_factor_enabled, two_factor_secret, two_factor_backup_codes, source, source_id, updated_at) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (
                    str(uuid.uuid4()), email, name, str(account.get('color') or '#3ef2b5')[:7], avatar,
                    'scrypt', '', password_hash, SCRYPT_N, SCRYPT_N, int(account.get('passwordScore') or 0),
                    created_at, last_login_at, password_changed_at, two_factor_enabled, two_factor_secret,
                    backup_json, 'desktop', source_id, now,
                ),
            )
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO orbita_imports (source, source_id, email_hash, status, detail, created_at) '
            'VALUES (%s, %s, %s, %s, %s, %s) '
            'ON DUPLICATE KEY UPDATE status = VALUES(status), detail = VALUES(detail), created_at = VALUES(created_at)',
            ('desktop', source_id, mask_email(email), status, None, now),
        )
    return {'status': status}
