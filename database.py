import sqlite3
import threading
from datetime import datetime, timedelta, timezone, time
from werkzeug.security import generate_password_hash, check_password_hash
from config import DB_PATH

MSK = timezone(timedelta(hours=3))

class Database:
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
        except:
            pass

        conn.commit()

    # ==================== АВТОРИЗАЦИЯ ====================
    def register_user(self, username, password, fio, role):
        conn = self._get_conn()
        cursor = conn.cursor()
        password_hash = generate_password_hash(password)
        user_id = str(username)

        try:
            cursor.execute(
                """
                INSERT INTO users 
                (user_id, username, password_hash, fio, role, approval_status) 
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, password_hash, fio, role, "pending")
            )
            conn.commit()
            return True, "Регистрация успешна. Ожидайте подтверждения администратора."
        except sqlite3.IntegrityError:
            return False, "Пользователь с таким логином уже существует"

    def login_user(self, username, password):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()

        if not row:
            return None, "Неверный логин или пароль"

        if not row["is_active"]:
            return None, "Аккаунт заблокирован. Обратитесь к администратору."

        if row["approval_status"] == "pending":
            return None, "Ваш аккаунт ещё не подтверждён администратором."

        if row["approval_status"] == "rejected":
            return None, "Ваш аккаунт был отклонён администратором."

        if not check_password_hash(row["password_hash"] or "", password):
            return None, "Неверный логин или пароль"

        return dict(row), None

    def change_password(self, user_id, old_password, new_password):
        """Меняет пароль пользователя"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

        if not row or not check_password_hash(row["password_hash"] or "", old_password):
            return False, "Неверный текущий пароль"

        new_hash = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (new_hash, user_id))
        conn.commit()
        return True, "Пароль успешно изменён"

    def reset_password_by_admin(self, user_id, new_password):
        """Админ сбрасывает пароль пользователю"""
        conn = self._get_conn()
        cursor = conn.cursor()
        new_hash = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (new_hash, user_id))
        conn.commit()

    def toggle_user_active(self, user_id):
        """Блокирует/разблокирует пользователя"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            new_val = 0 if row["is_active"] else 1
            cursor.execute("UPDATE users SET is_active = ? WHERE user_id = ?", (new_val, user_id))
            conn.commit()
            return new_val == 1
        return None

    def update_user_profile(self, user_id, new_fio=None, new_username=None):
        """Обновляет профиль пользователя"""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if new_fio:
                cursor.execute("UPDATE users SET fio = ? WHERE user_id = ?", (new_fio, user_id))
            if new_username:
                cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (new_username, user_id))
                cursor.execute("UPDATE users SET user_id = ? WHERE user_id = ?", (new_username, user_id))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_user_and_clean_schedule(self, user_id, fio):
        """Удаляет пользователя и его записи из расписания"""
        conn = self._get_conn()
        cursor = conn.cursor()

        # 1. Удаляем пользователя
        cursor.execute("DELETE FROM users WHERE user_id = ?", (str(user_id),))

        # 2. Чистим записи из расписания
        cursor.execute("SELECT id, slot1, slot2, slot3, slot4 FROM schedule")
        rows = cursor.fetchall()
        for row in rows:
            for i, slot in enumerate([row["slot1"], row["slot2"], row["slot3"], row["slot4"]]):
                if slot and slot.strip() == fio:
                    cursor.execute(
                        f"UPDATE schedule SET slot{i + 1} = '' WHERE id = ?",
                        (row["id"],)
                    )

        conn.commit()


    def get_user_by_id(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),))
        row = cursor.fetchone()

        if row:
            return {
                "id": row["user_id"],
                "username": row["username"],
                "role": row["role"],
                "fio": row["fio"],
                "perm_exempt": bool(row["perm_exempt"]),
                "is_active": bool(row["is_active"]),
                "approval_status": row["approval_status"],
                "created_at": row["created_at"]
            }

        return None

    def get_summary_cards(self):
        """Возвращает данные сводки в виде карточек по практикам"""
        from datetime import timedelta, timezone
        from config import PRACTICES, EXEMPT_MONTHS, MONTH_NAMES

        MSK = timezone(timedelta(hours=3))
        now = datetime.now(MSK)
        cy, cm = now.year, now.month

        users = self.get_all_users()
        schedule = self.get_all_schedule()
        cancels = self.get_all_cancels()

        # Собираем всех, кто может дежурить: студенты + руководители
        duty_people = []
        for u in users:
            role = u["role"]
            if role in PRACTICES or (role.startswith("Рук") and role[4:].strip() in PRACTICES):
                practice = role if role in PRACTICES else role[4:].strip()
                duty_people.append({
                    "user_id": u["user_id"],
                    "fio": u["fio"],
                    "role": role,
                    "practice": practice,
                    "is_ruk": role.startswith("Рук"),
                    "perm_exempt": u["perm_exempt"]
                })

        # Собираем записи в расписании
        shifts_by_fio = {}
        for row in schedule[1:]:
            try:
                d = datetime.strptime(row[0].strip(), "%d.%m.%Y")
                if d.year != cy:
                    continue
                for i in range(1, min(len(row), 5)):
                    fio = row[i].strip()
                    if fio:
                        if fio not in shifts_by_fio:
                            shifts_by_fio[fio] = {}
                        month = d.month
                        if month not in shifts_by_fio[fio]:
                            shifts_by_fio[fio][month] = []
                        shift_name = "1 смена" if i <= 2 else "2 смена"  # ← Исправлено
                        shifts_by_fio[fio][month].append({
                            "date": row[0].strip(),
                            "day": d.day,
                            "shift": shift_name,
                            "place": i
                        })
            except:
                pass

        # ✅ ИСПРАВЛЕНО: Собираем освобождения на месяц из cancels
        forgiven_by_fio = {}
        for row in cancels[1:]:
            if len(row) >= 5:
                fio = row[0].strip()
                target_date = row[3].strip()
                reason = row[4].strip()
                if target_date.startswith("Освобождение"):
                    try:
                        m_v, y_v = map(int, target_date.replace("Освобождение ", "").split("."))
                        if y_v == cy:
                            if fio not in forgiven_by_fio:
                                forgiven_by_fio[fio] = {}
                            forgiven_by_fio[fio][m_v] = reason
                    except:
                        pass

        # Собираем прощения на период
        forgiveness_by_fio = {}
        for f in self.get_active_forgiveness():
            forgiveness_by_fio[f["fio"]] = f

        # Формируем карточки по практикам
        cards_by_practice = {p: [] for p in PRACTICES}
        ALLOWED_MONTHS = [1, 2, 3, 4, 5, 6, 9, 10, 11, 12]

        for person in duty_people:
            fio = person["fio"]
            practice = person["practice"]

            card = {
                "user_id": person["user_id"],
                "fio": fio,
                "role": person["role"],
                "is_ruk": person["is_ruk"],
                "perm_exempt": person["perm_exempt"],
                "months": [],
                "total_shifts": 0,
                "status": ""
            }

            # ✅ ИСПРАВЛЕНО: Проверяем прощение на период для КАЖДОГО месяца
            forgiveness = forgiveness_by_fio.get(fio)

            for m in ALLOWED_MONTHS:
                # Проверяем, попадает ли месяц в период прощения
                is_month_forgiven = False
                if forgiveness:
                    try:
                        start_dt = datetime.strptime(forgiveness["start_date"], "%d.%m.%Y")
                        end_dt = datetime.strptime(forgiveness["end_date"], "%d.%m.%Y")
                        # Месяц попадает в период, если начало <= конец месяца И конец >= начало месяца
                        month_start = datetime(cy, m, 1)
                        if m == 12:
                            month_end = datetime(cy, 12, 31)
                        else:
                            month_end = datetime(cy, m + 1, 1) - timedelta(days=1)

                        if start_dt <= month_end and end_dt >= month_start:
                            is_month_forgiven = True
                    except:
                        pass

                month_data = {
                    "month": m,
                    "month_name": MONTH_NAMES[m - 1],
                    "shifts": shifts_by_fio.get(fio, {}).get(m, []),
                    "forgiven": forgiven_by_fio.get(fio, {}).get(m),  # ← Освобождение на месяц
                    "forgiven_period": is_month_forgiven,  # ← Прощение на период (для этого месяца)
                    "is_current": m == cm,
                    "is_exempt_month": m in EXEMPT_MONTHS
                }
                card["months"].append(month_data)
                card["total_shifts"] += len(month_data["shifts"])

            # Определяем статус
            if person["perm_exempt"]:
                card["status"] = "exempt"
            elif card["total_shifts"] > 0:
                card["status"] = "active"
            else:
                # Проверяем, есть ли освобождение/прощение в текущем месяце
                current_month_forgiven = forgiven_by_fio.get(fio, {}).get(cm)
                current_month_forgiven_period = False
                if forgiveness:
                    try:
                        start_dt = datetime.strptime(forgiveness["start_date"], "%d.%m.%Y")
                        end_dt = datetime.strptime(forgiveness["end_date"], "%d.%m.%Y")
                        month_start = datetime(cy, cm, 1)
                        if cm == 12:
                            month_end = datetime(cy, 12, 31)
                        else:
                            month_end = datetime(cy, cm + 1, 1) - timedelta(days=1)
                        if start_dt <= month_end and end_dt >= month_start:
                            current_month_forgiven_period = True
                    except:
                        pass

                if current_month_forgiven or current_month_forgiven_period:
                    card["status"] = "forgiven"
                else:
                    card["status"] = "lazy"

            cards_by_practice[practice].append(card)

        # Сортируем: сначала ленивые, потом активные, потом освобождённые
        status_order = {"lazy": 0, "active": 1, "forgiven": 2, "exempt": 3}
        for p in PRACTICES:
            cards_by_practice[p].sort(key=lambda x: (status_order.get(x["status"], 99), x["fio"]))

        return cards_by_practice

    def update_role(self, user_id, new_role):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (new_role, str(user_id)))
        conn.commit()

    def get_all_users(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY fio")
        return [dict(row) for row in cursor.fetchall()]

    def toggle_perm_exempt(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT perm_exempt FROM users WHERE user_id = ?", (str(user_id),))
        row = cursor.fetchone()
        if row:
            new_val = 0 if row["perm_exempt"] else 1
            cursor.execute("UPDATE users SET perm_exempt = ? WHERE user_id = ?", (new_val, str(user_id)))
            conn.commit()
            return new_val == 1
        return False

    def delete_user(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = ?", (str(user_id),))
        conn.commit()

    def get_user_practice(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE user_id = ?", (str(user_id),))
        row = cursor.fetchone()
        return row["role"] if row else ""

    def approve_user(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET approval_status = 'approved', is_active = 1 WHERE user_id = ?",
            (str(user_id),)
        )
        conn.commit()

    def reject_user(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET approval_status = 'rejected', is_active = 0 WHERE user_id = ?",
            (str(user_id),)
        )
        conn.commit()

    def get_pending_users(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE approval_status = 'pending' ORDER BY created_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    # ==================== РАСПИСАНИЕ ====================
    def get_day_data(self, date_str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT slot1, slot2, slot3, slot4 FROM schedule WHERE date_str = ?", (date_str,)
        )
        row = cursor.fetchone()
        if row:
            return [row["slot1"] or "", row["slot2"] or "", row["slot3"] or "", row["slot4"] or ""]
        return ["", "", "", ""]

    def book_slot(self, date_str, slot, fio):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM schedule WHERE date_str = ?", (date_str,))
        row = cursor.fetchone()
        if row:
            cursor.execute(f"UPDATE schedule SET slot{slot + 1} = ? WHERE date_str = ?", (fio, date_str))
        else:
            slots = ["", "", "", ""]
            slots[slot] = fio
            cursor.execute(
                "INSERT INTO schedule (date_str, slot1, slot2, slot3, slot4) VALUES (?, ?, ?, ?, ?)",
                (date_str, slots[0], slots[1], slots[2], slots[3])
            )
        conn.commit()
        return True

    def clear_slot(self, date_str, slot):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE schedule SET slot{slot + 1} = '' WHERE date_str = ?", (date_str,))
        conn.commit()
        return True

    def get_all_schedule(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM schedule ORDER BY date_str")
        rows = cursor.fetchall()
        result = [["Дата", "Место 1", "Место 2", "Место 3", "Место 4"]]
        for row in rows:
            result.append([
                row["date_str"],
                row["slot1"] or "", row["slot2"] or "",
                row["slot3"] or "", row["slot4"] or ""
            ])
        return result

    def get_schedule_data_for_calendar(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT date_str, slot1, slot2, slot3, slot4 FROM schedule")
        data = {}
        for row in cursor.fetchall():
            occupied = sum(1 for s in [row["slot1"], row["slot2"], row["slot3"], row["slot4"]] if s and s.strip())
            data[row["date_str"]] = occupied
        return data

    # ==================== ОТМЕНЫ ====================
    def add_cancel(self, fio, practice, cancel_date, target_date, reason):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO cancels (fio, practice, cancel_date, target_date, reason) VALUES (?, ?, ?, ?, ?)",
            (fio, practice, cancel_date, target_date, reason)
        )
        conn.commit()

    def get_all_cancels(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cancels ORDER BY id DESC")
        rows = cursor.fetchall()
        result = [["ФИО", "Практика", "Дата отмены", "Дата смены/Освобождение", "Причина"]]
        for row in rows:
            result.append([row["fio"], row["practice"], row["cancel_date"], row["target_date"], row["reason"]])
        return result

    # ==================== ЗАПРОСЫ НА ОТМЕНУ ====================
    def add_cancel_request(self, user_id, fio, practice, date_str, reason):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO cancel_requests (user_id, fio, practice, date_str, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, fio, practice, date_str, reason, datetime.now().strftime("%d.%m.%Y %H:%M"))
        )
        conn.commit()

    def get_pending_cancel_requests(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cancel_requests WHERE status = 'pending' ORDER BY id DESC")
        return [dict(row) for row in cursor.fetchall()]

    def approve_cancel_request(self, request_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cancel_requests WHERE id = ?", (request_id,))
        req = cursor.fetchone()
        if req:
            self._clear_slot_by_fio(req["date_str"], req["fio"])
            self.add_cancel(req["fio"], req["practice"], datetime.now().strftime("%d.%m.%Y"), req["date_str"],
                            req["reason"])
            cursor.execute("UPDATE cancel_requests SET status = 'approved' WHERE id = ?", (request_id,))
            conn.commit()
            return dict(req)
        return None

    def reject_cancel_request(self, request_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE cancel_requests SET status = 'rejected' WHERE id = ?", (request_id,))
        conn.commit()
        cursor.execute("SELECT * FROM cancel_requests WHERE id = ?", (request_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def _clear_slot_by_fio(self, date_str, fio):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, slot1, slot2, slot3, slot4 FROM schedule WHERE date_str = ?", (date_str,))
        row = cursor.fetchone()
        if row:
            for i, slot in enumerate([row["slot1"], row["slot2"], row["slot3"], row["slot4"]]):
                if slot and slot.strip() == fio:
                    cursor.execute(f"UPDATE schedule SET slot{i + 1} = '' WHERE id = ?", (row["id"],))
                    conn.commit()
                    return True
        return False

    def add_exemption(self, user_id, fio, start_date, end_date, reason):
        """Добавляет освобождение на период"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO exemptions (user_id, fio, start_date, end_date, reason)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, fio, start_date, end_date, reason)
        )
        conn.commit()

    def get_active_exemptions(self):
        """Возвращает активные освобождения (текущая дата между start и end)"""
        from datetime import datetime
        conn = self._get_conn()
        cursor = conn.cursor()
        today = datetime.now().strftime("%d.%m.%Y")
        cursor.execute(
            """
            SELECT * FROM exemptions 
            WHERE start_date <= ? AND end_date >= ?
            ORDER BY start_date DESC
            """,
            (today, today)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_user_exemptions(self, user_id):
        """Возвращает все освобождения пользователя"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM exemptions WHERE user_id = ? ORDER BY start_date DESC",
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def delete_exemption(self, exemption_id):
        """Удаляет освобождение"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM exemptions WHERE id = ?", (exemption_id,))
        conn.commit()

    def create_cancel_request(self, user_id, fio, practice, date_str, reason):
        """Создаёт запрос на отмену дежурства"""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Проверяем, нет ли уже активного запроса на эту дату
        cursor.execute(
            "SELECT id FROM cancel_requests WHERE user_id = ? AND date_str = ? AND status = 'pending'",
            (user_id, date_str)
        )
        if cursor.fetchone():
            return False, "Запрос на эту дату уже отправлен"

        cursor.execute(
            """INSERT INTO cancel_requests 
               (user_id, fio, practice, date_str, reason, created_at) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, fio, practice, date_str, reason,
             datetime.now().strftime("%d.%m.%Y %H:%M"))
        )
        conn.commit()
        return True, "Запрос отправлен руководителю"

    def get_user_cancel_requests(self, user_id):
        """Запросы конкретного пользователя (для его статистики)"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM cancel_requests WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_ruk_cancel_requests(self, practice):
        """Запросы студентов конкретной практики (для руководителя)"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM cancel_requests WHERE practice = ? AND status = 'pending' ORDER BY id DESC",
            (practice,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def approve_cancel_request(self, request_id):
        """Одобрить запрос на отмену"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cancel_requests WHERE id = ?", (request_id,))
        req = cursor.fetchone()

        if not req or req["status"] != "pending":
            return None

        # Удаляем запись из расписания
        cursor.execute(
            "SELECT id, slot1, slot2, slot3, slot4 FROM schedule WHERE date_str = ?",
            (req["date_str"],)
        )
        row = cursor.fetchone()
        if row:
            for i, slot in enumerate([row["slot1"], row["slot2"], row["slot3"], row["slot4"]]):
                if slot and slot.strip() == req["fio"]:
                    cursor.execute(
                        f"UPDATE schedule SET slot{i + 1} = '' WHERE id = ?",
                        (row["id"],)
                    )
                    break

        # Пишем в историю отмен
        cursor.execute(
            """INSERT INTO cancels 
               (fio, practice, cancel_date, target_date, reason) 
               VALUES (?, ?, ?, ?, ?)""",
            (req["fio"], req["practice"],
             datetime.now().strftime("%d.%m.%Y"),
             req["date_str"], req["reason"])
        )

        # Помечаем запрос как одобренный
        cursor.execute(
            "UPDATE cancel_requests SET status = 'approved' WHERE id = ?",
            (request_id,)
        )
        conn.commit()
        return dict(req)

    def reject_cancel_request(self, request_id):
        """Отклонить запрос на отмену"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cancel_requests SET status = 'rejected' WHERE id = ? AND status = 'pending'",
            (request_id,)
        )
        conn.commit()
        cursor.execute("SELECT * FROM cancel_requests WHERE id = ?", (request_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_user_role(self, user_id, new_role):
        """Меняет роль пользователя (только для админа)"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET role = ? WHERE user_id = ?",
            (new_role, str(user_id))
        )
        conn.commit()

    def checkin(self, user_id, fio, date_str, slot, checkin_time):
        """Отмечает приход на смену"""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Проверяем, нет ли уже чек-ина
        cursor.execute(
            "SELECT id FROM checkins WHERE user_id = ? AND date_str = ? AND slot = ?",
            (user_id, date_str, slot)
        )
        if cursor.fetchone():
            return False, "Вы уже отметили приход"

        shift = 1 if slot < 2 else 2
        cursor.execute(
            """INSERT INTO checkins 
               (user_id, fio, date_str, slot, shift, checkin_time) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, fio, date_str, slot, shift, checkin_time)
        )
        conn.commit()
        return True, f"Приход отмечен в {checkin_time}"

    def get_user_checkins(self, user_id):
        """Все чек-ины пользователя"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM checkins WHERE user_id = ? ORDER BY date_str DESC",
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_checkin_for_slot(self, date_str, slot, fio):
        """Чек-ин для конкретного слота"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM checkins WHERE date_str = ? AND slot = ? AND fio = ?",
            (date_str, slot, fio)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_checkins_for_date(self, date_str):
        """Все чек-ины на конкретную дату"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM checkins WHERE date_str = ?",
            (date_str,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_shift_status(self, date_str, slot):
        """
        Возвращает статус смены:
        - future: смена в будущем
        - can_checkin: сейчас окно чек-ина
        - missed: окно прошло, чек-ина нет
        - present: есть чек-ин
        """
        try:
            shift_date = datetime.strptime(date_str, "%d.%m.%Y").date()
            today = datetime.now(MSK).date()
            now_time = datetime.now(MSK).time()

            # Определяем время смены
            if slot < 2:
                window_start = time(10, 00)  # ← было (9, 45)
                window_end = time(12, 00)  # ← было (12, 30)
            else:
                window_start = time(13, 00)  # ← было (12, 45)
                window_end = time(16, 00)

            if shift_date > today:
                return "future"
            elif shift_date < today:
                return "past"
            else:  # сегодня
                if now_time < window_start:
                    return "future_today"
                elif window_start <= now_time <= window_end:
                    return "can_checkin"
                else:
                    return "missed"
        except:
            return "unknown"

    # ==================== СВОДКА ====================
    def get_summary_data(self):
        from datetime import timedelta, timezone
        from config import PRACTICES, EXEMPT_MONTHS, MONTH_NAMES

        MSK = timezone(timedelta(hours=3))
        now = datetime.now(MSK)
        cy, cm = now.year, now.month

        users = self.get_all_users()
        schedule = self.get_all_schedule()
        cancels = self.get_all_cancels()

        fios_by_p = {p: [] for p in PRACTICES + ["Все"]}
        user_stats = {}

        for u in users:
            p, fio = u["role"], u["fio"]
            is_perm = u["perm_exempt"]
            if p in PRACTICES:
                fios_by_p[p].append(fio)
                fios_by_p["Все"].append(fio)
                user_stats[fio] = {
                    'shifts': {}, 'forgiven': {}, 'start': None,
                    'practice': p, 'perm_exempt': is_perm
                }

        for r in schedule[1:]:
            try:
                d = datetime.strptime(r[0].strip(), "%d.%m.%Y")
                for i in range(1, min(len(r), 5)):
                    f = r[i].strip()
                    if f in user_stats:
                        if user_stats[f]['start'] is None or d < user_stats[f]['start']:
                            user_stats[f]['start'] = d
                        if d.year == cy:
                            user_stats[f]['shifts'].setdefault(d.month, []).append(r[0].strip())
            except:
                pass

        for r in cancels[1:]:
            if len(r) >= 5:
                f, val, reas = r[0].strip(), r[3].strip(), r[4].strip()
                if f in user_stats and val.startswith("Освобождение"):
                    try:
                        m_v, y_v = map(int, val.replace("Освобождение ", "").split("."))
                        if y_v == cy:
                            user_stats[f]['forgiven'][m_v] = reas
                    except:
                        pass

        def gen_rows(fio_list):
            ALLOWED = [1, 2, 3, 4, 5, 6, 9, 10, 11, 12]
            res = []
            for f in fio_list:
                st = user_stats[f]
                rd = [f, st['practice']]
                for m in ALLOWED:
                    if st['perm_exempt']:
                        rd.append("🌟 Вечное")
                    elif m in st['shifts']:
                        rd.append(", ".join(st['shifts'][m]))
                    elif m in st['forgiven']:
                        rd.append(f"освобожден ({st['forgiven'][m]})")
                    elif m == cm:
                        rd.append("⚠️ Не записан")
                    elif m > cm or m in EXEMPT_MONTHS:
                        rd.append("")
                    elif st['start'] is None or (st['start'].year == cy and m < st['start'].month):
                        rd.append("-")
                    else:
                        rd.append("❌ Пропуск")
                res.append(rd)
            return res

        headers = ["ФИО", "Практика"] + MONTH_NAMES[:6] + MONTH_NAMES[8:]
        return {
            "headers": headers,
            "all": gen_rows(fios_by_p["Все"]),
            "by_practice": {p: gen_rows(fios_by_p[p]) for p in PRACTICES}
        }

    def get_all_forgiveness_by_practice(self, practice):
        """Все прощения практики (включая прошедшие)"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM forgiveness WHERE practice = ? ORDER BY id DESC",
            (practice,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def add_forgiveness_period(self, user_id, fio, practice, start_date, end_date, reason):
        """Добавляет прощение на период"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO forgiveness 
               (user_id, fio, practice, start_date, end_date, reason) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, fio, practice, start_date, end_date, reason)
        )
        conn.commit()

    def get_active_forgiveness(self):
        """Возвращает активные прощения (текущая дата между start и end)"""
        conn = self._get_conn()
        cursor = conn.cursor()
        today = datetime.now().strftime("%d.%m.%Y")
        cursor.execute(
            """SELECT * FROM forgiveness 
               WHERE start_date <= ? AND end_date >= ?
               ORDER BY start_date DESC""",
            (today, today)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_forgiveness_by_fio(self, fio):
        """Возвращает все прощения конкретного пользователя"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM forgiveness WHERE fio = ? ORDER BY start_date DESC",
            (fio,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def delete_forgiveness(self, forgiveness_id):
        """Удаляет прощение"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM forgiveness WHERE id = ?", (forgiveness_id,))
        conn.commit()

    def is_date_forgiven(self, fio, date_str):
        """Проверяет, прощена ли конкретная дата для пользователя"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM forgiveness 
               WHERE fio = ? AND start_date <= ? AND end_date >= ?""",
            (fio, date_str, date_str)
        )
        return cursor.fetchone() is not None




db = Database()