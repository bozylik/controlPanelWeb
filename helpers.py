"""Общие хелперы, используемые во всех маршрутах"""
from flask import session
from database import db
from config import PRACTICES, EXEMPT_MONTHS, MONTH_NAMES
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))


def is_admin(role):
    return role.lower() in ['admin', 'админ']


def is_ruk(role):
    return role.lower().startswith("рук")


def get_managed_practice(user):
    """
    Возвращает практику, которой управляет пользователь:
    - "ALL"  — администратор (все практики)
    - "ГП"   — руководитель практики ГП
    - None   — нет прав на управление отчётами
    """
    if user is None:
        return None
    if is_admin(user["role"]):
        return "ALL"
    if is_ruk(user["role"]):
        return user["role"][4:].strip()
    return None


def get_current_user():
    uid = session.get("user_id")
    if uid:
        return db.get_user_by_id(uid)
    return None


def check_user_reminders(user):
    """Проверяет напоминания при входе"""
    messages = []
    if user["role"] not in PRACTICES or user["perm_exempt"]:
        return messages

    now = datetime.now(MSK)

    # 1. Завтра дежурство
    tomorrow = (now + timedelta(days=1)).strftime("%d.%m.%Y")
    tmr_data = db.get_day_data(tomorrow)
    if user["fio"] in [s.strip() for s in tmr_data]:
        slot = [s.strip() for s in tmr_data].index(user["fio"])
        shift = "1 смена" if slot < 2 else "2 смена"
        messages.append(f"🔔 Завтра ({tomorrow}) у вас дежурство ({shift})!")

    # 2. 10-го числа — нет дежурств в этом месяце
    if now.day == 10 and now.month not in EXEMPT_MONTHS:
        all_schedule = db.get_all_schedule()
        month_str = f".{now.month:02d}.{now.year}"
        has_shift = any(
            month_str in row[0] and user["fio"] in [f.strip() for f in row[1:5]]
            for row in all_schedule[1:]
        )
        if not has_shift:
            messages.append("🔔 В этом месяце у вас еще нет дежурств!")

    # 3. 25-го числа — не записался на следующий месяц
    if now.day == 25:
        nm = now.month + 1 if now.month < 12 else 1
        ny = now.year if now.month < 12 else now.year + 1
        if nm not in EXEMPT_MONTHS:
            all_schedule = db.get_all_schedule()
            month_str = f".{nm:02d}.{ny}"
            has_shift = any(
                month_str in row[0] and user["fio"] in [f.strip() for f in row[1:5]]
                for row in all_schedule[1:]
            )
            if not has_shift:
                messages.append(f"🔔 Вы еще не записались на дежурство в {MONTH_NAMES[nm-1]}!")

    return messages