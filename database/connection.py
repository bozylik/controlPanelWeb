"""Подключение к БД (Turso/LibSQL или локальный SQLite)"""
import sqlite3
import threading
from datetime import timedelta, timezone

import config

# Часовой пояс Москвы (МСК = UTC+3)
MSK = timezone(timedelta(hours=3))

# Определяем движок
USE_TURSO = bool(config.TURSO_DATABASE_URL and config.TURSO_AUTH_TOKEN)

if USE_TURSO:
    try:
        import libsql.experimental as libsql
    except ImportError:
        raise RuntimeError(
            "Для работы с Turso установи пакет: pip install libsql-experimental"
        )


class ConnectionMixin:
    def __init__(self):
        self.local = threading.local()

    def _get_conn(self):
        if not hasattr(self.local, 'conn') or self.local.conn is None:
            if USE_TURSO:
                self.local.conn = libsql.connect(
                    config.TURSO_DATABASE_URL,
                    auth_token=config.TURSO_AUTH_TOKEN,
                )
                # LibSQL возвращает Row-подобные объекты,
                # row_factory задаётся не так, как в sqlite3,
                # но в libsql-experimental по умолчанию dict-подобный доступ работает.
                # Чтобы dict(row) работал как раньше — используем row_factory.
                try:
                    self.local.conn.row_factory = libsql.Row
                except AttributeError:
                    pass
            else:
                self.local.conn = sqlite3.connect(config.DB_PATH)
                self.local.conn.row_factory = sqlite3.Row
        return self.local.conn

    def init(self):
        """Создаёт таблицы. Executescript в LibSQL работает не везде —
        создаём таблицы по одной."""
        conn = self._get_conn()
        cursor = conn.cursor()

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
                cursor.execute(sql)
            except Exception as e:
                print(f"⚠️ Таблица: {e}")

        # Миграция: добавить approval_status, если его нет
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN approval_status TEXT DEFAULT 'pending'")
        except Exception:
            pass  # уже есть

        conn.commit()
        print(f"✅ БД готова (движок: {'Turso' if USE_TURSO else 'SQLite'})")