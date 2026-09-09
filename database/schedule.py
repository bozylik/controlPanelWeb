"""Расписание: дни, слоты, бронирование"""


class ScheduleMixin:
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