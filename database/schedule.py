"""Расписание: дни, слоты, бронирование"""


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


class ScheduleMixin:
    def get_day_data(self, date_str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT slot1, slot2, slot3, slot4 FROM schedule WHERE date_str = ?", (date_str,)
        )
        row = _to_dict(cursor, cursor.fetchone())
        if row:
            return [row.get("slot1") or "", row.get("slot2") or "", row.get("slot3") or "", row.get("slot4") or ""]
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
        if hasattr(conn, "commit"):
            conn.commit()
        return True

    def clear_slot(self, date_str, slot):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE schedule SET slot{slot + 1} = '' WHERE date_str = ?", (date_str,))
        if hasattr(conn, "commit"):
            conn.commit()
        return True

    def get_all_schedule(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM schedule ORDER BY date_str")
        rows = _to_dict_list(cursor, cursor.fetchall())
        result = [["Дата", "Место 1", "Место 2", "Место 3", "Место 4"]]
        for row in rows:
            result.append([
                row.get("date_str"),
                row.get("slot1") or "", row.get("slot2") or "",
                row.get("slot3") or "", row.get("slot4") or ""
            ])
        return result

    def get_schedule_data_for_calendar(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT date_str, slot1, slot2, slot3, slot4 FROM schedule")
        rows = _to_dict_list(cursor, cursor.fetchall())
        data = {}
        for row in rows:
            occupied = sum(
                1 for s in [row.get("slot1"), row.get("slot2"), row.get("slot3"), row.get("slot4")]
                if s and s.strip()
            )
            data[row["date_str"]] = occupied
        return data

    def _clear_slot_by_fio(self, date_str, fio):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, slot1, slot2, slot3, slot4 FROM schedule WHERE date_str = ?", (date_str,))
        row = _to_dict(cursor, cursor.fetchone())
        if row:
            for i, slot in enumerate([row.get("slot1"), row.get("slot2"), row.get("slot3"), row.get("slot4")]):
                if slot and slot.strip() == fio:
                    cursor.execute(f"UPDATE schedule SET slot{i + 1} = '' WHERE id = ?", (row["id"],))
                    if hasattr(conn, "commit"):
                        conn.commit()
                    return True
        return False