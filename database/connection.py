"""Подключение к БД и инициализация таблиц"""
import sqlite3
import threading
from datetime import timedelta, timezone

from config import DB_PATH

# Часовой пояс Москвы (МСК = UTC+3)
MSK = timezone(timedelta(hours=3))


class ConnectionMixin:
    def __init__(self):
        self.local = threading.local()

    def _get_conn(self):
        if not hasattr(self.local, 'conn'):
            self.local.conn = sqlite3.connect(DB_PATH)
            self.local.conn.row_factory = sqlite3.Row
        return self.local.conn

    def init(self):
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS users (
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
            );

            CREATE TABLE IF NOT EXISTS schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_str TEXT UNIQUE NOT NULL,
                slot1 TEXT DEFAULT '',
                slot2 TEXT DEFAULT '',
                slot3 TEXT DEFAULT '',
                slot4 TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS cancels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fio TEXT NOT NULL,
                practice TEXT DEFAULT '',
                cancel_date TEXT NOT NULL,
                target_date TEXT NOT NULL,
                reason TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS cancel_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fio TEXT NOT NULL,
                practice TEXT DEFAULT '',
                date_str TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exemptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fio TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                reason TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS forgiveness (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fio TEXT NOT NULL,
                practice TEXT DEFAULT '',
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                reason TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS checkins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                fio TEXT NOT NULL,
                date_str TEXT NOT NULL,
                slot INTEGER NOT NULL,
                shift INTEGER NOT NULL,
                checkin_time TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # Миграции для существующей БД
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN approval_status TEXT DEFAULT 'pending'")
        except sqlite3.OperationalError:
            pass

        conn.commit()