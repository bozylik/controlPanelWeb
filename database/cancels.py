"""Отмены дежурств и запросы на отмену"""
from datetime import datetime


def _to_dict(cursor, row):
    """Преобразует строку БД (tuple или Row) в обычный dict."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys"):
        return dict(row)
    # Если вернулся обычный tuple/list (бывает в LibSQL)
    if hasattr(cursor, "description") and cursor.description:
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row))
    return dict(row)


def _to_dict_list(cursor, rows):
    """Преобразует список строк БД в список словарей."""
    return [_to_dict(cursor, row) for row in rows]


class CancelsMixin:
    # ==================== ИСТОРИЯ ОТМЕН ====================
    def add_cancel(self, fio, practice, cancel_date, target_date, reason):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO cancels (fio, practice, cancel_date, target_date, reason) VALUES (?, ?, ?, ?, ?)",
            (fio, practice, cancel_date, target_date, reason)
        )
        if hasattr(conn, "commit"):
            conn.commit()

    def get_all_cancels(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cancels ORDER BY id DESC")
        rows = cursor.fetchall()

        result = [["ФИО", "Практика", "Дата отмены", "Дата смены/Освобождение", "Причина"]]
        for row in rows:
            d = _to_dict(cursor, row)
            result.append([d["fio"], d["practice"], d["cancel_date"], d["target_date"], d["reason"]])
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
        if hasattr(conn, "commit"):
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
        return _to_dict_list(cursor, cursor.fetchall())

    def get_ruk_cancel_requests(self, practice):
        """Запросы студентов конкретной практики (для руководителя)"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM cancel_requests WHERE practice = ? AND status = 'pending' ORDER BY id DESC",
            (practice,)
        )
        return _to_dict_list(cursor, cursor.fetchall())

    def get_pending_cancel_requests(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cancel_requests WHERE status = 'pending' ORDER BY id DESC")
        return _to_dict_list(cursor, cursor.fetchall())

    def approve_cancel_request(self, request_id):
        """Одобрить запрос на отмену"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cancel_requests WHERE id = ?", (request_id,))
        req = cursor.fetchone()

        if not req or req["status"] != "pending":
            return None

        # Определяем номер места для уведомления
        day_data = self.get_day_data(req["date_str"])
        place_num = None
        for i, slot in enumerate(day_data):
            if slot and slot.strip() == req["fio"]:
                place_num = i + 1
                break

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

        result = dict(req)
        # ✅ Добавляем номер места в результат для шаблона
        result["place_num"] = place_num
        return result

    def reject_cancel_request(self, request_id):
        """Отклонить запрос на отмену"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE cancel_requests SET status = 'rejected' WHERE id = ? AND status = 'pending'",
            (request_id,)
        )
        if hasattr(conn, "commit"):
            conn.commit()

        cursor.execute("SELECT * FROM cancel_requests WHERE id = ?", (request_id,))
        row = cursor.fetchone()
        return _to_dict(cursor, row)