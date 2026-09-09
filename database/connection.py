"""Подключение к БД (Turso/LibSQL или локальный SQLite)"""
import sqlite3
import threading
from datetime import timedelta, timezone

import config

MSK = timezone(timedelta(hours=3))

USE_TURSO = bool(config.TURSO_DATABASE_URL and config.TURSO_AUTH_TOKEN)

if USE_TURSO:
    try:
        from libsql import connect as libsql_connect
    except ImportError:
        raise RuntimeError(
            "Для работы с Turso установи: pip install libsql"
        )


class DictLikeRow(dict):
    """Обертка для результата LibSQL, позволяющая обращаться и по ключу, и по индексу."""
    def __init__(self, mapping, tuple_data):
        super().__init__(mapping)
        self._tuple = tuple_data

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._tuple[item]
        return super().__getitem__(item)


class LibSQLCursorWrapper:
    """Обертка над курсором LibSQL для автоматического преобразования строк в словари."""
    def __init__(self, cursor):
        self._cursor = cursor

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def _wrap_row(self, row):
        if row is None:
            return None
        if isinstance(row, dict):
            return row
        if hasattr(self._cursor, "description") and self._cursor.description:
            cols = [col[0] for col in self._cursor.description]
            mapping = dict(zip(cols, row))
            return DictLikeRow(mapping, row)
        return row

    def fetchone(self):
        row = self._cursor.fetchone()
        return self._wrap_row(row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [self._wrap_row(r) for r in rows]


class LibSQLConnWrapper:
    """Обертка над подключением LibSQL для проброса обернутого курсора."""
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def cursor(self):
        return LibSQLCursorWrapper(self._conn.cursor())

    def execute(self, *args, **kwargs):
        cursor = self._conn.execute(*args, **kwargs)
        return LibSQLCursorWrapper(cursor)


class ConnectionMixin:
    def __init__(self):
        self.local = threading.local()

    def _get_conn(self):
        if not hasattr(self.local, 'conn') or self.local.conn is None:
            if USE_TURSO:
                raw_conn = libsql_connect(
                    config.TURSO_DATABASE_URL,
                    auth_token=config.TURSO_AUTH_TOKEN,
                )
                self.local.conn = LibSQLConnWrapper(raw_conn)
            else:
                self.local.conn = sqlite3.connect(config.DB_PATH)
                self.local.conn.row_factory = sqlite3.Row
        return self.local.conn

    def init(self):
        """Создаёт таблицы. Для LibSQL — по одной с явным commit()."""
        conn = self._get_conn()

        tables = [
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                username TEXT UNIQUE,
                password_hash TEXT,
                fio TEXT NOT NULL,
                role TEXT NOT NULL,
                perm_exempt INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                approval_status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_str TEXT UNIQUE NOT NULL,
                slot1 TEXT DEFAULT '',
                slot2 TEXT DEFAULT '',
                slot3 TEXT DEFAULT '',
                slot4 TEXT DEFAULT ''
            )""",
            """CREATE TABLE IF NOT EXISTS cancels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fio TEXT NOT NULL,
                practice TEXT DEFAULT '',
                cancel_date TEXT NOT NULL,
                target_date TEXT NOT NULL,
                reason TEXT DEFAULT ''
            )""",
            """CREATE TABLE IF NOT EXISTS cancel_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fio TEXT NOT NULL,
                practice TEXT DEFAULT '',
                date_str TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS exemptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fio TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                reason TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS forgiveness (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fio TEXT NOT NULL,
                practice TEXT DEFAULT '',
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                reason TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS checkins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fio TEXT NOT NULL,
                date_str TEXT NOT NULL,
                slot INTEGER NOT NULL,
                shift INTEGER NOT NULL,
                checkin_time TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""",
        ]

        for sql in tables:
            try:
                conn.execute(sql)
                if hasattr(conn, "commit"):
                    conn.commit()
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"⚠️ {e}")

        # Миграция: approval_status для старых БД
        try:
            conn.execute("ALTER TABLE users ADD COLUMN approval_status TEXT DEFAULT 'pending'")
            if hasattr(conn, "commit"):
                conn.commit()
        except Exception:
            pass  # колонка уже есть или таблица только что создана с ней

        print(f"✅ БД готова (движок: {'Turso' if USE_TURSO else 'SQLite'})")