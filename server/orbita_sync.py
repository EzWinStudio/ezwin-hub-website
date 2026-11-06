import re
import time

CHANNEL_PATTERN = re.compile(r'^[A-Za-z0-9_-]{22,64}$')
MAX_PAYLOAD = 600_000
MAX_DEVICE = 80

_SCHEMA_READY = False

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS orbita_sync_blobs (
      channel_id VARCHAR(64) NOT NULL PRIMARY KEY,
      payload MEDIUMTEXT NOT NULL,
      version INT NOT NULL,
      updated_at BIGINT NOT NULL,
      device_id VARCHAR(80) NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


def now_ms():
    return int(time.time() * 1000)


def valid_channel(value):
    return isinstance(value, str) and bool(CHANNEL_PATTERN.match(value))


def ensure_schema(conn):
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with conn.cursor() as cur:
        for statement in SCHEMA_STATEMENTS:
            cur.execute(statement)
    _SCHEMA_READY = True


def current(conn, channel):
    with conn.cursor() as cur:
        cur.execute(
            'SELECT channel_id, payload, version, updated_at FROM orbita_sync_blobs WHERE channel_id = %s LIMIT 1',
            (channel,),
        )
        return cur.fetchone()


def get_blob(conn, channel):
    row = current(conn, channel)
    if not row:
        return {'ok': True, 'found': False, 'version': 0, 'updatedAt': 0}
    return {
        'ok': True,
        'found': True,
        'payload': row['payload'],
        'version': int(row['version']),
        'updatedAt': int(row['updated_at']),
    }


def put_blob(conn, channel, payload, expected_version, device_id):
    now = now_ms()
    device = (device_id or '')[:MAX_DEVICE] or None
    if expected_version == 0:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT IGNORE INTO orbita_sync_blobs (channel_id, payload, version, updated_at, device_id) '
                'VALUES (%s, %s, 1, %s, %s)',
                (channel, payload, now, device),
            )
            inserted = cur.rowcount == 1
        if inserted:
            return {'ok': True, 'version': 1, 'updatedAt': now}
        existing = current(conn, channel)
        return {
            'ok': False,
            'code': 'sync_conflict',
            'version': int(existing['version']) if existing else 0,
            'updatedAt': int(existing['updated_at']) if existing else 0,
        }

    with conn.cursor() as cur:
        cur.execute(
            'UPDATE orbita_sync_blobs SET payload = %s, version = version + 1, updated_at = %s, device_id = %s '
            'WHERE channel_id = %s AND version = %s',
            (payload, now, device, channel, expected_version),
        )
        updated = cur.rowcount == 1
    if updated:
        return {'ok': True, 'version': expected_version + 1, 'updatedAt': now}
    existing = current(conn, channel)
    return {
        'ok': False,
        'code': 'sync_conflict',
        'version': int(existing['version']) if existing else 0,
        'updatedAt': int(existing['updated_at']) if existing else 0,
    }
