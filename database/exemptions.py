"""Освобождения и прощения на период"""
from datetime import datetime


class ExemptionsMixin:
    # ==================== ОСВОБОЖДЕНИЯ ====================
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
        """Активные освобождения (сегодня внутри периода). Даты сравниваются в Python."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM exemptions ORDER BY id DESC")
        rows = [dict(row) for row in cursor.fetchall()]

        today = datetime.now().date()
        result = []
        for e in rows:
            try:
                start = datetime.strptime(e["start_date"], "%d.%m.%Y").date()
                end = datetime.strptime(e["end_date"], "%d.%m.%Y").date()
                if start <= today <= end:
                    result.append(e)
            except (ValueError, KeyError, TypeError):
                continue
        return result

    def get_user_exemptions(self, user_id):
        """Все освобождения пользователя"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM exemptions WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def delete_exemption(self, exemption_id):
        """Удаляет освобождение"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM exemptions WHERE id = ?", (exemption_id,))
        conn.commit()

    # ==================== ПРОЩЕНИЯ ====================
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

    def get_all_forgiveness(self):
        """Все прощения без фильтра"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM forgiveness ORDER BY id DESC")
        return [dict(row) for row in cursor.fetchall()]

    def get_all_forgiveness_by_practice(self, practice):
        """Все прощения практики (включая прошедшие)"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM forgiveness WHERE practice = ? ORDER BY id DESC",
            (practice,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_active_forgiveness(self):
        """Активные прощения (сегодня внутри периода). Даты сравниваются в Python."""
        today = datetime.now().date()
        result = []
        for f in self.get_all_forgiveness():
            try:
                start = datetime.strptime(f["start_date"], "%d.%m.%Y").date()
                end = datetime.strptime(f["end_date"], "%d.%m.%Y").date()
                if start <= today <= end:
                    result.append(f)
            except (ValueError, KeyError, TypeError):
                continue
        return result

    def get_forgiveness_by_fio(self, fio):
        """Все прощения конкретного пользователя"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM forgiveness WHERE fio = ? ORDER BY id DESC",
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
        try:
            target = datetime.strptime(date_str, "%d.%m.%Y").date()
        except ValueError:
            return False
        for f in self.get_forgiveness_by_fio(fio):
            try:
                start = datetime.strptime(f["start_date"], "%d.%m.%Y").date()
                end = datetime.strptime(f["end_date"], "%d.%m.%Y").date()
                if start <= target <= end:
                    return True
            except (ValueError, KeyError, TypeError):
                continue
        return False