"""Отмены дежурств и запросы на отмену"""
from datetime import datetime


class CancelsMixin:
    # ==================== ИСТОРИЯ ОТМЕН ====================
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

    def get_pending_cancel_requests(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cancel_requests WHERE status = 'pending' ORDER BY id DESC")
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
        self._clear_slot_by_fio(req["date_str"], req["fio"])

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