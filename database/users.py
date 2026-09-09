"""Пользователи: регистрация, вход, роли, подтверждение"""
import sqlite3

from werkzeug.security import generate_password_hash, check_password_hash


def _to_dict(cursor, row):
    """Преобразует строку БД (tuple или Row) в обычный dict."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys"):
        return dict(row)
    if hasattr(cursor, "description") and cursor.description:
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row))
    return dict(row)


def _to_dict_list(cursor, rows):
    """Преобразует список строк БД в список словарей."""
    return [_to_dict(cursor, row) for row in rows]


class UsersMixin:
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
            if hasattr(conn, "commit"):
                conn.commit()
            return True, "Регистрация успешна. Ожидайте подтверждения администратора."
        except Exception as e:
            if "UNIQUE" in str(e).upper() or isinstance(e, sqlite3.IntegrityError):
                return False, "Пользователь с таким логином уже существует"
            raise e

    def login_user(self, username, password):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = _to_dict(cursor, cursor.fetchone())

        if not row:
            return None, "Неверный логин или пароль"

        if not row.get("is_active"):
            return None, "Аккаунт заблокирован. Обратитесь к администратору."

        if row.get("approval_status") == "pending":
            return None, "Ваш аккаунт ещё не подтверждён администратором."

        if row.get("approval_status") == "rejected":
            return None, "Ваш аккаунт был отклонён администратором."

        if not check_password_hash(row.get("password_hash") or "", password):
            return None, "Неверный логин или пароль"

        return row, None

    def change_password(self, user_id, old_password, new_password):
        """Меняет пароль пользователя"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT password_hash FROM users WHERE user_id = ?",
            (str(user_id),)
        )
        row = _to_dict(cursor, cursor.fetchone())

        if not row:
            return False, "Пользователь не найден"

        current_hash = row.get("password_hash") or ""
        if not current_hash:
            return False, "Пароль не задан. Обратитесь к администратору."

        # Проверяем текущий пароль (защищено от падений)
        try:
            if not check_password_hash(current_hash, old_password):
                return False, "Неверный текущий пароль"
        except (ValueError, TypeError):
            return False, "Неверный текущий пароль"

        new_hash = generate_password_hash(new_password)
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE user_id = ?",
            (new_hash, str(user_id))
        )
        if hasattr(conn, "commit"):
            conn.commit()
        return True, "Пароль успешно изменён"

    def reset_password_by_admin(self, user_id, new_password):
        """Админ сбрасывает пароль пользователю"""
        conn = self._get_conn()
        cursor = conn.cursor()
        new_hash = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (new_hash, str(user_id)))
        if hasattr(conn, "commit"):
            conn.commit()

    def toggle_user_active(self, user_id):
        """Блокирует/разблокирует пользователя"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM users WHERE user_id = ?", (str(user_id),))
        row = _to_dict(cursor, cursor.fetchone())
        if row:
            new_val = 0 if row.get("is_active") else 1
            cursor.execute("UPDATE users SET is_active = ? WHERE user_id = ?", (new_val, str(user_id)))
            if hasattr(conn, "commit"):
                conn.commit()
            return new_val == 1
        return None

    def update_user_profile(self, user_id, new_fio=None, new_username=None):
        """Обновляет профиль пользователя"""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if new_fio:
                cursor.execute("UPDATE users SET fio = ? WHERE user_id = ?", (new_fio, str(user_id)))
            if new_username:
                cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (new_username, str(user_id)))
                cursor.execute("UPDATE users SET user_id = ? WHERE user_id = ?", (new_username, str(user_id)))
            if hasattr(conn, "commit"):
                conn.commit()
            return True
        except Exception:
            return False

    def delete_user_and_clean_schedule(self, user_id, fio):
        """Удаляет пользователя и его записи из расписания"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM users WHERE user_id = ?", (str(user_id),))

        cursor.execute("SELECT id, slot1, slot2, slot3, slot4 FROM schedule")
        rows = _to_dict_list(cursor, cursor.fetchall())
        for row in rows:
            for i, slot in enumerate([row.get("slot1"), row.get("slot2"), row.get("slot3"), row.get("slot4")]):
                if slot and slot.strip() == fio:
                    cursor.execute(
                        f"UPDATE schedule SET slot{i + 1} = '' WHERE id = ?",
                        (row.get("id"),)
                    )

        if hasattr(conn, "commit"):
            conn.commit()

    def get_user_by_id(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),))
        row = _to_dict(cursor, cursor.fetchone())

        if row:
            return {
                "id": row.get("user_id"),
                "username": row.get("username"),
                "role": row.get("role"),
                "fio": row.get("fio"),
                "perm_exempt": bool(row.get("perm_exempt")),
                "is_active": bool(row.get("is_active")),
                "approval_status": row.get("approval_status"),
                "created_at": row.get("created_at")
            }

        return None

    def get_all_users(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY fio")
        return _to_dict_list(cursor, cursor.fetchall())

    def toggle_perm_exempt(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT perm_exempt FROM users WHERE user_id = ?", (str(user_id),))
        row = _to_dict(cursor, cursor.fetchone())
        if row:
            new_val = 0 if row.get("perm_exempt") else 1
            cursor.execute("UPDATE users SET perm_exempt = ? WHERE user_id = ?", (new_val, str(user_id)))
            if hasattr(conn, "commit"):
                conn.commit()
            return new_val == 1
        return False

    def delete_user(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = ?", (str(user_id),))
        if hasattr(conn, "commit"):
            conn.commit()

    def get_user_practice(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE user_id = ?", (str(user_id),))
        row = _to_dict(cursor, cursor.fetchone())
        return row.get("role", "") if row else ""

    def approve_user(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET approval_status = 'approved', is_active = 1 WHERE user_id = ?",
            (str(user_id),)
        )
        if hasattr(conn, "commit"):
            conn.commit()

    def reject_user(self, user_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET approval_status = 'rejected', is_active = 0 WHERE user_id = ?",
            (str(user_id),)
        )
        if hasattr(conn, "commit"):
            conn.commit()

    def get_pending_users(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE approval_status = 'pending' ORDER BY created_at DESC"
        )
        return _to_dict_list(cursor, cursor.fetchall())

    def update_user_role(self, user_id, new_role):
        """Меняет роль пользователя (только для админа)"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET role = ? WHERE user_id = ?",
            (new_role, str(user_id))
        )
        if hasattr(conn, "commit"):
            conn.commit()