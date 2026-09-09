"""Статистика пользователя и отмена дежурств"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import db
from config import EXEMPT_MONTHS, MONTH_NAMES
from helpers import get_current_user, is_admin, is_ruk, MSK
from datetime import datetime

stats_bp = Blueprint('stats', __name__)


@stats_bp.route("/cancel_duty", methods=["GET", "POST"])
def cancel_duty():
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        date_str = request.form.get("date")
        reason = request.form.get("reason", "").strip()
        if date_str and reason:
            now = datetime.now(MSK)
            day_data = db.get_day_data(date_str)
            for i, slot in enumerate(day_data):
                if slot.strip() == user["fio"]:
                    db.clear_slot(date_str, i)
                    break
            practice = db.get_user_practice(user["id"])
            db.add_cancel(user["fio"], practice, now.strftime("%d.%m.%Y"), date_str, reason)
            flash(f"Дежурство {date_str} отменено", "success")
            return redirect(url_for("calendar.calendar_view"))

    now_msk = datetime.now(MSK)
    today = datetime(now_msk.year, now_msk.month, now_msk.day)
    all_schedule = db.get_all_schedule()
    future = []
    for row in all_schedule[1:]:
        if len(row) >= 2:
            row_fios = [f.strip() for f in row[1:5]]
            if user["fio"] in row_fios:
                try:
                    dt = datetime.strptime(row[0].strip(), "%d.%m.%Y")
                    if dt >= today:
                        future.append(row[0].strip())
                except:
                    pass
    return render_template("cancel_duty.html", user=user, future_shifts=future)


@stats_bp.route("/stats")
def stats():
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))

    if is_admin(user["role"]) or is_ruk(user["role"]):
        flash("Статистика дежурств доступна только студентам", "error")
        return redirect(url_for("calendar.calendar_view"))

    now_msk = datetime.now(MSK)
    today = now_msk.date()

    all_schedule = db.get_all_schedule()
    all_cancels = db.get_all_cancels()
    user_checkins = db.get_user_checkins(user["id"])

    checkins_dict = {
        (c["date_str"], c["slot"]): c
        for c in user_checkins
    }

    user_shifts = []
    for row in all_schedule[1:]:
        if len(row) < 2:
            continue

        row_fios = [f.strip() for f in row[1:5]]

        for slot_index, fio_in_slot in enumerate(row_fios):
            if fio_in_slot != user["fio"]:
                continue

            try:
                date = datetime.strptime(row[0].strip(), "%d.%m.%Y")
                date_str = row[0].strip()
                is_past = date.date() < today

                shift_name = "1 смена (10:00-12:00)" if slot_index < 2 else "2 смена (13:00-16:00)"

                checkin = checkins_dict.get((date_str, slot_index))
                shift_over = db.is_shift_over(date_str, slot_index)
                if checkin:
                    checkin_status = "present"
                    checkin_time = checkin["checkin_time"]
                elif shift_over:
                    checkin_status = "missed"
                    checkin_time = None
                else:
                    checkin_status = "upcoming"
                    checkin_time = None

                user_shifts.append({
                    "date": date,
                    "date_str": date_str,
                    "shift": shift_name,
                    "place": slot_index + 1,
                    "is_past": is_past,
                    "checkin_status": checkin_status,
                    "checkin_time": checkin_time
                })
            except (ValueError, IndexError):
                pass

    user_shifts.sort(key=lambda x: x["date"], reverse=True)

    present_count = sum(1 for s in user_shifts if s["checkin_status"] == "present")
    missed_count = sum(1 for s in user_shifts if s["checkin_status"] == "missed")
    completed = present_count + missed_count
    attendance_rate = round(present_count / completed * 100, 1) if completed > 0 else 0.0

    cancelled = []
    forgiven = {}
    for row in all_cancels[1:]:
        if len(row) < 5 or row[0].strip() != user["fio"]:
            continue

        target = row[3].strip()
        reason = row[4].strip()

        if target.startswith("Освобождение"):
            try:
                m, y = map(int, target.replace("Освобождение ", "").split("."))
                forgiven[(y, m)] = reason
            except (ValueError, IndexError):
                pass
        else:
            cancelled.append({"date": target, "reason": reason})

    missed = []
    if user_shifts and not user["perm_exempt"]:
        user_dates = [s["date"] for s in user_shifts]
        user_months = {(d.year, d.month) for d in user_dates}

        cur_y, cur_m = min(user_dates).year, min(user_dates).month
        while (cur_y, cur_m) <= (now_msk.year, now_msk.month):
            if (cur_y, cur_m) not in user_months \
                    and (cur_y, cur_m) not in forgiven \
                    and cur_m not in EXEMPT_MONTHS:
                missed.append(f"{MONTH_NAMES[cur_m - 1]} {cur_y}")

            cur_m += 1
            if cur_m > 12:
                cur_m, cur_y = 1, cur_y + 1

    my_requests = db.get_user_cancel_requests(user["id"])
    pending_requests = [r for r in my_requests if r["status"] == "pending"]
    processed_requests = [r for r in my_requests if r["status"] != "pending"]

    return render_template(
        "stats.html",
        user=user,
        shifts=user_shifts,
        missed=missed,
        forgiven=forgiven,
        cancelled=cancelled,
        pending_requests=pending_requests,
        processed_requests=processed_requests,
        present_count=present_count,
        missed_count=missed_count,
        attendance_rate=attendance_rate,
        MONTH_NAMES=MONTH_NAMES
    )


@stats_bp.route("/unbook_from_stats/<date_str>", methods=["POST"])
def unbook_from_stats(date_str):
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))

    try:
        day_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        today = datetime.now(MSK).date()
        if day_date < today:
            flash("Нельзя отменить прошедшее дежурство", "error")
            return redirect(url_for("stats.stats"))
    except:
        flash("Некорректная дата", "error")
        return redirect(url_for("stats.stats"))

    reason = request.form.get("reason", "").strip()
    if not reason:
        flash("Укажите причину отмены", "error")
        return redirect(url_for("stats.stats"))

    if is_admin(user["role"]):
        day_data = db.get_day_data(date_str)
        for i, slot in enumerate(day_data):
            if slot.strip() == user["fio"]:
                db.clear_slot(date_str, i)
                break
        practice = db.get_user_practice(user["id"])
        db.add_cancel(user["fio"], practice,
                      datetime.now(MSK).strftime("%d.%m.%Y"),
                      date_str, reason + " (отменено админом)")
        flash(f"Дежурство {date_str} отменено", "success")
        return redirect(url_for("stats.stats"))

    practice = db.get_user_practice(user["id"])
    success, msg = db.create_cancel_request(
        user["id"], user["fio"], practice, date_str, reason
    )
    flash(msg, "success" if success else "error")
    return redirect(url_for("stats.stats"))