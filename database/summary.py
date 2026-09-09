"""Сводки: карточки по практикам и таблица для CSV"""
from datetime import datetime, timedelta

from config import PRACTICES, EXEMPT_MONTHS, MONTH_NAMES

from .connection import MSK


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


def _month_range(year, month):
    """Начало и конец месяца"""
    month_start = datetime(year, month, 1)
    if month == 12:
        month_end = datetime(year, 12, 31)
    else:
        month_end = datetime(year, month + 1, 1) - timedelta(days=1)
    return month_start, month_end


def _forgiveness_intersects_month(forgiveness, year, month):
    """Пересекается ли прощение с месяцем"""
    try:
        f_start = datetime.strptime(forgiveness["start_date"], "%d.%m.%Y")
        f_end = datetime.strptime(forgiveness["end_date"], "%d.%m.%Y")
    except (ValueError, KeyError, TypeError):
        return False
    month_start, month_end = _month_range(year, month)
    return f_start <= month_end and f_end >= month_start


def _forgiveness_covers_date(forgiveness, target_date):
    """Покрывает ли прощение конкретную дату"""
    try:
        f_start = datetime.strptime(forgiveness["start_date"], "%d.%m.%Y").date()
        f_end = datetime.strptime(forgiveness["end_date"], "%d.%m.%Y").date()
    except (ValueError, KeyError, TypeError):
        return False
    return f_start <= target_date <= f_end


class SummaryMixin:
    def get_summary_cards(self):
        """Возвращает данные сводки в виде карточек по практикам"""
        now = datetime.now(MSK)
        cy, cm = now.year, now.month

        users = self.get_all_users()
        schedule = self.get_all_schedule()
        cancels = self.get_all_cancels()

        # Собираем всех, кто может дежурить: студенты + руководители
        duty_people = []
        for u in users:
            role = u.get("role", "")
            if role in PRACTICES or (role.startswith("Рук") and role[4:].strip() in PRACTICES):
                practice = role if role in PRACTICES else role[4:].strip()
                duty_people.append({
                    "user_id": u.get("user_id"),
                    "fio": u.get("fio"),
                    "role": role,
                    "practice": practice,
                    "is_ruk": role.startswith("Рук"),
                    "perm_exempt": u.get("perm_exempt", 0)
                })

        # Освобождения на месяц (legacy-формат из cancels)
        forgiven_by_fio = {}
        for row in cancels[1:]:
            if len(row) >= 5:
                fio = str(row[0]).strip()
                target_date = str(row[3]).strip()
                reason = str(row[4]).strip()
                if target_date.startswith("Освобождение"):
                    try:
                        m_v, y_v = map(int, target_date.replace("Освобождение ", "").split("."))
                        if y_v == cy:
                            forgiven_by_fio.setdefault(fio, {})[m_v] = reason
                    except ValueError:
                        pass

        # Все прощения на период, сгруппированные по ФИО
        forgiveness_by_fio = {}
        for f in self.get_all_forgiveness():
            forgiveness_by_fio.setdefault(f["fio"], []).append(f)

        # ✅ Множество чек-инов для быстрой проверки (корректная обработка tuple/dict из Turso)
        checkins_set = set()
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT fio, date_str, slot FROM checkins")
        for row in cursor.fetchall():
            d = _to_dict(cursor, row)
            if isinstance(row, (tuple, list)):
                checkins_set.add((row[0], row[1], row[2]))
            elif d:
                checkins_set.add((d.get("fio"), d.get("date_str"), d.get("slot")))

        # ✅ Записи расписания со статусом явки
        shifts_by_fio = {}
        for row in schedule[1:]:
            try:
                date_str = str(row[0]).strip()
                d = datetime.strptime(date_str, "%d.%m.%Y")
                if d.year != cy:
                    continue
                for i in range(1, min(len(row), 5)):
                    fio = str(row[i]).strip()
                    if not fio:
                        continue

                    slot0 = i - 1
                    has_checkin = (fio, date_str, slot0) in checkins_set
                    over = self.is_shift_over(date_str, slot0)
                    forgiven_date = any(
                        _forgiveness_covers_date(f, d.date())
                        for f in forgiveness_by_fio.get(fio, [])
                    )

                    if has_checkin:
                        checkin_status = "present"
                    elif over:
                        checkin_status = "forgiven" if forgiven_date else "missed"
                    else:
                        checkin_status = "upcoming"

                    shifts_by_fio.setdefault(fio, {}).setdefault(d.month, []).append({
                        "date": date_str,
                        "day": d.day,
                        "shift": "1 смена" if i <= 2 else "2 смена",
                        "place": i,
                        "checkin_status": checkin_status,
                    })
            except ValueError:
                pass

        # Формируем карточки по практикам
        cards_by_practice = {p: [] for p in PRACTICES}
        ALLOWED_MONTHS = [1, 2, 3, 4, 5, 6, 9, 10, 11, 12]

        for person in duty_people:
            fio = person["fio"]
            practice = person["practice"]
            person_forgiveness = forgiveness_by_fio.get(fio, [])

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

            for m in ALLOWED_MONTHS:
                is_month_forgiven = any(
                    _forgiveness_intersects_month(f, cy, m) for f in person_forgiveness
                )
                month_data = {
                    "month": m,
                    "month_name": MONTH_NAMES[m - 1],
                    "shifts": shifts_by_fio.get(fio, {}).get(m, []),
                    "forgiven": forgiven_by_fio.get(fio, {}).get(m),
                    "forgiven_period": is_month_forgiven,
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
                current_month_forgiven = forgiven_by_fio.get(fio, {}).get(cm)
                current_month_forgiven_period = any(
                    _forgiveness_intersects_month(f, cy, cm) for f in person_forgiveness
                )
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

    def get_summary_data(self):
        """Табличная сводка для CSV-экспорта"""
        now = datetime.now(MSK)
        cy, cm = now.year, now.month

        users = self.get_all_users()
        schedule = self.get_all_schedule()
        cancels = self.get_all_cancels()

        fios_by_p = {p: [] for p in PRACTICES + ["Все"]}
        user_stats = {}

        for u in users:
            p, fio = u.get("role"), u.get("fio")
            is_perm = u.get("perm_exempt", 0)
            if p in PRACTICES:
                fios_by_p[p].append(fio)
                fios_by_p["Все"].append(fio)
                user_stats[fio] = {
                    'shifts': {}, 'forgiven': {}, 'start': None,
                    'practice': p, 'perm_exempt': is_perm
                }

        for r in schedule[1:]:
            try:
                d = datetime.strptime(str(r[0]).strip(), "%d.%m.%Y")
                for i in range(1, min(len(r), 5)):
                    f = str(r[i]).strip()
                    if f in user_stats:
                        if user_stats[f]['start'] is None or d < user_stats[f]['start']:
                            user_stats[f]['start'] = d
                        if d.year == cy:
                            user_stats[f]['shifts'].setdefault(d.month, []).append(str(r[0]).strip())
            except ValueError:
                pass

        for r in cancels[1:]:
            if len(r) >= 5:
                f, val, reas = str(r[0]).strip(), str(r[3]).strip(), str(r[4]).strip()
                if f in user_stats and val.startswith("Освобождение"):
                    try:
                        m_v, y_v = map(int, val.replace("Освобождение ", "").split("."))
                        if y_v == cy:
                            user_stats[f]['forgiven'][m_v] = reas
                    except ValueError:
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