"""Календарь и просмотр дня"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import db
from config import MONTH_NAMES
from helpers import get_current_user, is_admin, is_ruk, MSK
from datetime import datetime
import calendar as cal_module

calendar_bp = Blueprint('calendar', __name__)


@calendar_bp.route("/calendar")
@calendar_bp.route("/calendar/<int:year>/<int:month>")
def calendar_view(year=None, month=None):
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))

    now = datetime.now(MSK)
    if year is None: year = now.year
    if month is None: month = now.month

    schedule_data = db.get_schedule_data_for_calendar()
    today = now.date()

    weeks = cal_module.monthcalendar(year, month)
    calendar_weeks = []
    for week in weeks:
        work_days = week[:5]
        if sum(work_days) == 0: continue
        days = []
        for day in work_days:
            if day == 0:
                days.append({"day": 0, "date": "", "occupied": 0, "is_past": False})
            else:
                date_str = f"{day:02d}.{month:02d}.{year}"
                occupied = schedule_data.get(date_str, 0)
                try:
                    day_date = datetime.strptime(date_str, "%d.%m.%Y").date()
                    is_past = day_date < today
                except:
                    is_past = False
                days.append({
                    "day": day,
                    "date": date_str,
                    "occupied": occupied,
                    "is_past": is_past
                })
        calendar_weeks.append(days)

    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1

    today_str = now.strftime("%d.%m.%Y")
    today_data = db.get_day_data(today_str)

    return render_template("calendar.html", user=user, weeks=calendar_weeks,
                           month_name=MONTH_NAMES[month - 1],
                           year=year, month=month,
                           prev_y=prev_y, prev_m=prev_m,
                           next_y=next_y, next_m=next_m,
                           today=today_str, today_data=today_data,
                           is_admin=is_admin(user["role"]),
                           is_ruk=is_ruk(user["role"]))


@calendar_bp.route("/day/<date_str>")
def day_view(date_str):
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))

    try:
        day_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        today = datetime.now(MSK).date()
        is_past = day_date < today
    except:
        is_past = False

    day_data = db.get_day_data(date_str)

    slots_info = []
    for i in range(4):
        fio = day_data[i].strip() if i < len(day_data) else ""
        status = db.get_shift_status(date_str, i) if fio else "empty"
        checkin = db.get_checkin_for_slot(date_str, i, fio) if fio else None

        slots_info.append({
            "fio": fio,
            "status": status,
            "checkin": checkin,
            "is_mine": fio == user["fio"]
        })

    return render_template("day.html",
                           user=user,
                           date_str=date_str,
                           day_data=day_data,
                           slots_info=slots_info,
                           is_admin=is_admin(user["role"]),
                           is_ruk=is_ruk(user["role"]),
                           is_past=is_past)


@calendar_bp.route("/book/<date_str>/<int:slot>")
def book_slot(date_str, slot):
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))

    # Защита: админ не может записываться
    if is_admin(user["role"]):
        flash("Администратор не может записываться на дежурства", "error")
        return redirect(url_for("calendar.day_view", date_str=date_str))

    # Защита: руководитель не может записываться
    if is_ruk(user["role"]):
        flash("Руководитель практики не может записываться на дежурства", "error")
        return redirect(url_for("calendar.day_view", date_str=date_str))

    try:
        booking_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        today = datetime.now(MSK).date()
        if booking_date < today:
            flash("Нельзя записаться на прошедший день", "error")
            return redirect(url_for("calendar.calendar_view"))
    except ValueError:
        flash("Некорректная дата", "error")
        return redirect(url_for("calendar.calendar_view"))

    day_data = db.get_day_data(date_str)

    # ✅ НОВОЕ: нельзя записаться дважды на одну смену
    requested_shift = 1 if slot < 2 else 2
    shift_slots = range(0, 2) if requested_shift == 1 else range(2, 4)

    for s in shift_slots:
        if day_data[s].strip() == user["fio"]:
            shift_label = "1 смену (10:00-12:00)" if requested_shift == 1 else "2 смену (13:00-16:00)"
            flash(f"Вы уже записаны на {shift_label} в этот день. Выберите другую смену.", "error")
            return redirect(url_for("calendar.day_view", date_str=date_str))

    # Защита: нельзя занять уже занятое место
    if day_data[slot].strip():
        flash("Это место уже занято", "error")
        return redirect(url_for("calendar.day_view", date_str=date_str))

    if db.book_slot(date_str, slot, user["fio"]):
        shift_name = "1 смена" if slot < 2 else "2 смена"
        flash(f"Вы записаны на {date_str}, {shift_name}, место {slot + 1}!", "success")
    else:
        flash("Ошибка при бронировании", "error")
    return redirect(url_for("calendar.day_view", date_str=date_str))


@calendar_bp.route("/unbook/<date_str>/<int:slot>")
def unbook_slot(date_str, slot):
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))
    day_data = db.get_day_data(date_str)
    if day_data[slot].strip() == user["fio"] or is_admin(user["role"]):
        db.clear_slot(date_str, slot)
        flash("Запись удалена", "success")
    else:
        flash("Вы можете удалить только свою запись", "error")
    return redirect(url_for("calendar.day_view", date_str=date_str))