"""Чек-ины: отметки прихода на смену"""
from datetime import datetime, time

from .connection import MSK


class CheckinsMixin:
    def checkin(self, user_id, fio, date_str, slot, checkin_time):
        """Отмечает приход на смену"""
        conn = self._get_conn()
        cursor = conn.cursor()

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
        """Возвращает статус смены"""
        try:
            shift_date = datetime.strptime(date_str, "%d.%m.%Y").date()
            today = datetime.now(MSK).date()
            now_time = datetime.now(MSK).time()

            if slot < 2:
                window_start = time(10, 0)
                window_end = time(12, 0)
            else:
                window_start = time(13, 0)
                window_end = time(16, 0)

            if shift_date > today:
                return "future"
            elif shift_date < today:
                return "past"
            else:
                if now_time < window_start:
                    return "future_today"
                elif window_start <= now_time <= window_end:
                    return "can_checkin"
                else:
                    return "missed"
        except ValueError:
            return "unknown"

    # ✅ НОВОЕ: проверка, прошла ли смена
    def is_shift_over(self, date_str, slot):
        """Прошла ли смена целиком (включая окно чек-ина)"""
        try:
            shift_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        except ValueError:
            return False

        today = datetime.now(MSK).date()
        if shift_date < today:
            return True
        if shift_date > today:
            return False

        # Сегодня: смена прошла, если окно чек-ина закрылось
        now_time = datetime.now(MSK).time()
        window_end = time(12, 0) if slot < 2 else time(16, 0)
        return now_time > window_end