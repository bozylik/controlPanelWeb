"""Отчёты по практикам: для руководителя и администратора"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import db
from config import PRACTICES, MONTH_NAMES
from helpers import get_current_user, is_admin, get_managed_practice, MSK
from datetime import datetime, timedelta

ruk_bp = Blueprint('ruk', __name__)


def _month_bounds(year, month):
    month_start = datetime(year, month, 1).date()
    if month == 12:
        month_end = datetime(year, 12, 31).date()
    else:
        month_end = datetime(year, month + 1, 1).date() - timedelta(days=1)
    return month_start, month_end


def _collect_report(target_p, month, year):
    """Собирает все данные отчёта по одной практике."""
    now = datetime.now(MSK)
    all_users = db.get_all_users()
    all_schedule = db.get_all_schedule()
    all_cancels = db.get_all_cancels()

    # Освобождения текущего месяца (legacy)
    forgiven_this_month = {}
    target_str = f"Освобождение {month:02d}.{year}"
    for r in all_cancels[1:]:
        if len(r) >= 5 and r[3].strip() == target_str:
            forgiven_this_month[r[0].strip()] = r[4].strip()

    # История отмен
    all_cancels_by_fio = {}
    for r in all_cancels[1:]:
        if len(r) >= 5:
            fio = r[0].strip()
            all_cancels_by_fio.setdefault(fio, []).append({
                "cancel_date": r[2].strip(),
                "target": r[3].strip(),
                "reason": r[4].strip()
            })

    # Чек-ины за месяц
    target_m_str = f".{month:02d}.{year}"
    checkins_by_fio = {}
    conn = db._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM checkins WHERE date_str LIKE ?", (f'%{target_m_str}',))
    for row in cursor.fetchall():
        row_dict = dict(row)
        checkins_by_fio.setdefault(row_dict["fio"], []).append(row_dict)

    # Прощения, пересекающие выбранный месяц
    month_start, month_end = _month_bounds(year, month)
    active_forgiveness_my = []
    forgiveness_periods = []
    for f in db.get_all_forgiveness_by_practice(target_p):
        try:
            f_start = datetime.strptime(f["start_date"], "%d.%m.%Y").date()
            f_end = datetime.strptime(f["end_date"], "%d.%m.%Y").date()
        except (ValueError, KeyError):
            continue
        if f_start <= month_end and f_end >= month_start:
            active_forgiveness_my.append(f)
            forgiveness_periods.append((f["fio"], f_start, f_end))

    def is_date_forgiven(person_fio, shift_date):
        for f_fio, f_start, f_end in forgiveness_periods:
            if f_fio == person_fio and f_start <= shift_date <= f_end:
                return True
        return False

    total_students = 0
    active_students = 0
    lazy_students = 0
    exempt_students = 0
    practice_present = 0
    practice_missed = 0

    students = []
    for u in all_users:
        if u["role"] != target_p:
            continue

        fio = u["fio"]
        is_perm = u["perm_exempt"]
        total_students += 1

        student_data = {
            "user_id": u["user_id"],
            "fio": fio,
            "perm_exempt": is_perm,
            "forgiven_this_month": forgiven_this_month.get(fio),
            "shifts": [],
            "cancels": all_cancels_by_fio.get(fio, []),
            "status": "",
            "present_count": 0,
            "missed_count": 0,
            "forgiven_count": 0,
            "attendance_rate": 0.0,
        }

        if is_perm:
            student_data["status"] = "exempt"
            exempt_students += 1
        elif student_data["forgiven_this_month"]:
            student_data["status"] = "forgiven"
            exempt_students += 1
        else:
            for s in all_schedule[1:]:
                if len(s) >= 2 and target_m_str in s[0]:
                    row_fios = [f.strip() for f in s[1:5]]
                    for slot_index, fio_in_slot in enumerate(row_fios):
                        if fio_in_slot != fio:
                            continue

                        shift_name = "1 смена (10:00-12:00)" if slot_index < 2 else "2 смена (13:00-16:00)"
                        date_str = s[0].strip()

                        checkin = None
                        for c in checkins_by_fio.get(fio, []):
                            if c["date_str"] == date_str and c["slot"] == slot_index:
                                checkin = c
                                break

                        shift_over = db.is_shift_over(date_str, slot_index)

                        if checkin:
                            checkin_status = "present"
                            checkin_time = checkin["checkin_time"]
                            student_data["present_count"] += 1
                            practice_present += 1
                        elif shift_over and is_date_forgiven(
                                fio, datetime.strptime(date_str, "%d.%m.%Y").date()):
                            checkin_status = "forgiven"
                            checkin_time = None
                            student_data["forgiven_count"] += 1
                        elif shift_over:
                            checkin_status = "missed"
                            checkin_time = None
                            student_data["missed_count"] += 1
                            practice_missed += 1
                        else:
                            checkin_status = "upcoming"
                            checkin_time = None

                        student_data["shifts"].append({
                            "date": date_str,
                            "day": int(date_str.split('.')[0]),
                            "shift": shift_name,
                            "place": slot_index + 1,
                            "checkin_status": checkin_status,
                            "checkin_time": checkin_time
                        })

            student_data["shifts"].sort(key=lambda x: x["date"])

            completed = student_data["present_count"] + student_data["missed_count"]
            if completed > 0:
                student_data["attendance_rate"] = round(
                    student_data["present_count"] / completed * 100, 1
                )
            elif student_data["forgiven_count"] > 0:
                student_data["attendance_rate"] = 100.0

            if student_data["shifts"]:
                student_data["status"] = "booked"
                active_students += 1
            else:
                student_data["status"] = "missing"
                lazy_students += 1

        students.append(student_data)

    status_order = {"missing": 0, "booked": 1, "forgiven": 2, "exempt": 3}
    students.sort(key=lambda x: (status_order.get(x["status"], 99), x["fio"]))

    # Освобождения на период (активные сегодня) для студентов практики
    all_active_exemptions = db.get_active_exemptions()
    my_students_fios = {s["fio"] for s in students}
    active_exemptions_my = [e for e in all_active_exemptions if e["fio"] in my_students_fios]

    pending_cancel_requests = db.get_ruk_cancel_requests(target_p)

    practice_completed = practice_present + practice_missed
    practice_attendance_rate = round(
        practice_present / practice_completed * 100, 1
    ) if practice_completed > 0 else 0.0

    return {
        "students": students,
        "total_students": total_students,
        "active_students": active_students,
        "lazy_students": lazy_students,
        "exempt_students": exempt_students,
        "practice_present": practice_present,
        "practice_missed": practice_missed,
        "practice_attendance_rate": practice_attendance_rate,
        "active_exemptions": active_exemptions_my,
        "active_forgiveness": active_forgiveness_my,
        "pending_cancel_requests": pending_cancel_requests,
    }


def _nav_months(month, year):
    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1
    return prev_m, prev_y, next_m, next_y


@ruk_bp.route("/ruk_report")
@ruk_bp.route("/ruk_report/<int:month>/<int:year>")
def ruk_report(month=None, year=None):
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))

    managed = get_managed_practice(user)
    if managed is None:
        return redirect(url_for("calendar.calendar_view"))

    now = datetime.now(MSK)
    if month is None: month = now.month
    if year is None: year = now.year

    prev_m, prev_y, next_m, next_y = _nav_months(month, year)
    nav = dict(prev_m=prev_m, prev_y=prev_y, next_m=next_m, next_y=next_y,
               month=month, year=year, month_name=MONTH_NAMES[month - 1])

    # Админ: выбор практики; "all" = обзор по всем
    if managed == "ALL":
        requested = request.args.get("practice", "all")
        if requested == "all" or requested not in PRACTICES:
            overview = []
            for p in PRACTICES:
                data = _collect_report(p, month, year)
                overview.append({
                    "practice": p,
                    "total_students": data["total_students"],
                    "active_students": data["active_students"],
                    "lazy_students": data["lazy_students"],
                    "exempt_students": data["exempt_students"],
                    "practice_present": data["practice_present"],
                    "practice_missed": data["practice_missed"],
                    "practice_attendance_rate": data["practice_attendance_rate"],
                })
            return render_template("ruk_overview.html", user=user, overview=overview,
                                   practices=PRACTICES, **nav)
        target_p = requested
        is_admin_view = True
    else:
        target_p = managed
        is_admin_view = False

    data = _collect_report(target_p, month, year)

    return render_template(
        "ruk_report.html",
        user=user,
        target_p=target_p,
        is_admin_view=is_admin_view,
        practices=PRACTICES,
        current_practice=(target_p if is_admin_view else None),
        **nav,
        **data
    )


@ruk_bp.route("/ruk_delete_student/<user_id>")
def ruk_delete_student(user_id):
    user = get_current_user()
    managed = get_managed_practice(user)
    if managed is None:
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar.calendar_view"))

    if user["id"] == user_id:
        flash("Нельзя удалить самого себя", "error")
        return redirect(url_for("ruk.ruk_report"))

    target = db.get_user_by_id(user_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("ruk.ruk_report"))

    if is_admin(target["role"]) or target["role"].lower().startswith("рук"):
        flash("Нельзя удалить администратора или руководителя", "error")
        return redirect(url_for("ruk.ruk_report"))

    if managed != "ALL" and target["role"] != managed:
        flash(f"Можно удалять только студентов практики {managed}", "error")
        return redirect(url_for("ruk.ruk_report"))

    db.delete_user_and_clean_schedule(user_id, target["fio"])
    flash(f"Студент {target['fio']} удалён", "success")
    return redirect(url_for("ruk.ruk_report"))


@ruk_bp.route("/ruk_remove_shift/<date_str>/<int:slot>", methods=["POST"])
def ruk_remove_shift(date_str, slot):
    user = get_current_user()
    managed = get_managed_practice(user)
    if managed is None:
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar.calendar_view"))

    day_data = db.get_day_data(date_str)
    if slot >= len(day_data) or not day_data[slot].strip():
        flash("Это место уже свободно", "error")
        return redirect(url_for("ruk.ruk_report"))

    status = db.get_shift_status(date_str, slot)
    if status in ["past", "missed"]:
        flash("Эта смена уже завершена. Факт явки/неявки неизменяем. "
              "Используйте прощение, чтобы снять отметку 'не явился'.", "error")
        return redirect(url_for("ruk.ruk_report"))

    target_fio = day_data[slot].strip()

    target = None
    for u in db.get_all_users():
        if u["fio"] == target_fio:
            target = u
            break

    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("ruk.ruk_report"))

    if managed != "ALL" and target["role"] != managed:
        flash(f"Можно удалять записи только студентов практики {managed}", "error")
        return redirect(url_for("ruk.ruk_report"))

    reason = request.form.get("reason", "").strip()
    marker = "администратором" if managed == "ALL" else f"руководителем {managed}"
    full_reason = f"{reason} (удалено {marker})" if reason else f"Удалено {marker}"

    db.clear_slot(date_str, slot)
    db.add_cancel(target_fio, target["role"],
                  datetime.now(MSK).strftime("%d.%m.%Y"), date_str, full_reason)

    flash(f"Запись {target_fio} на {date_str} удалена", "success")
    return redirect(url_for("ruk.ruk_report"))


@ruk_bp.route("/ruk_add_exemption", methods=["POST"])
def ruk_add_exemption():
    user = get_current_user()
    managed = get_managed_practice(user)
    if managed is None:
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar.calendar_view"))

    target_id = request.form.get("target_id")
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()
    reason = request.form.get("reason", "").strip()

    if not target_id or not start_date or not end_date:
        flash("Заполните все поля", "error")
        return redirect(url_for("ruk.ruk_report"))

    target = db.get_user_by_id(target_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("ruk.ruk_report"))

    if managed != "ALL" and target["role"] != managed:
        flash(f"Можно выдавать освобождения только студентам практики {managed}", "error")
        return redirect(url_for("ruk.ruk_report"))

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if end_dt < start_dt:
            flash("Дата окончания должна быть позже даты начала", "error")
            return redirect(url_for("ruk.ruk_report"))
        start_fmt = start_dt.strftime("%d.%m.%Y")
        end_fmt = end_dt.strftime("%d.%m.%Y")
    except ValueError:
        flash("Некорректный формат даты", "error")
        return redirect(url_for("ruk.ruk_report"))

    if not reason:
        reason = "Освобождение на период"

    db.add_exemption(target_id, target["fio"], start_fmt, end_fmt, reason)
    flash(f"Освобождение для {target['fio']} добавлено ({start_fmt} — {end_fmt})", "success")
    return redirect(url_for("ruk.ruk_report"))


@ruk_bp.route("/ruk_delete_exemption/<int:exemption_id>")
def ruk_delete_exemption(exemption_id):
    user = get_current_user()
    managed = get_managed_practice(user)
    if managed is None:
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar.calendar_view"))

    conn = db._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM exemptions WHERE id = ?", (exemption_id,))
    exemption = cursor.fetchone()

    if not exemption:
        flash("Освобождение не найдено", "error")
        return redirect(url_for("ruk.ruk_report"))

    if managed != "ALL":
        cursor.execute("SELECT role FROM users WHERE user_id = ?", (exemption["user_id"],))
        role_row = cursor.fetchone()
        if not role_row or role_row["role"] != managed:
            flash("Можно удалять освобождения только студентов своей практики", "error")
            return redirect(url_for("ruk.ruk_report"))

    db.delete_exemption(exemption_id)
    flash("Освобождение удалено", "success")
    return redirect(url_for("ruk.ruk_report"))


@ruk_bp.route("/approve_cancel/<int:request_id>")
def approve_cancel(request_id):
    user = get_current_user()
    managed = get_managed_practice(user)
    if managed is None:
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar.calendar_view"))

    conn = db._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cancel_requests WHERE id = ?", (request_id,))
    req = cursor.fetchone()

    if not req or (managed != "ALL" and req["practice"] != managed):
        flash("Можно одобрять только запросы своих студентов", "error")
        return redirect(url_for("ruk.ruk_report"))

    result = db.approve_cancel_request(request_id)
    if result:
        flash(f"Запрос {result['fio']} на {result['date_str']} одобрен", "success")
    else:
        flash("Ошибка при одобрении", "error")
    return redirect(url_for("ruk.ruk_report"))


@ruk_bp.route("/reject_cancel/<int:request_id>")
def reject_cancel(request_id):
    user = get_current_user()
    managed = get_managed_practice(user)
    if managed is None:
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar.calendar_view"))

    conn = db._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cancel_requests WHERE id = ?", (request_id,))
    req = cursor.fetchone()

    if not req or (managed != "ALL" and req["practice"] != managed):
        flash("Можно отклонять только запросы своих студентов", "error")
        return redirect(url_for("ruk.ruk_report"))

    result = db.reject_cancel_request(request_id)
    if result:
        flash(f"Запрос {result['fio']} на {result['date_str']} отклонён", "error")
    else:
        flash("Ошибка при отклонении", "error")
    return redirect(url_for("ruk.ruk_report"))


@ruk_bp.route("/ruk_forgive_period", methods=["POST"])
def ruk_forgive_period():
    user = get_current_user()
    managed = get_managed_practice(user)
    if managed is None:
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar.calendar_view"))

    target_id = request.form.get("target_id")
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()
    reason = request.form.get("reason", "").strip()

    if not target_id or not start_date or not end_date:
        flash("Заполните все поля", "error")
        return redirect(url_for("ruk.ruk_report"))

    target = db.get_user_by_id(target_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("ruk.ruk_report"))

    if managed != "ALL" and target["role"] != managed:
        flash(f"Можно прощать только студентов практики {managed}", "error")
        return redirect(url_for("ruk.ruk_report"))

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if end_dt < start_dt:
            flash("Дата окончания должна быть позже даты начала", "error")
            return redirect(url_for("ruk.ruk_report"))
        start_fmt = start_dt.strftime("%d.%m.%Y")
        end_fmt = end_dt.strftime("%d.%m.%Y")
    except ValueError:
        flash("Некорректный формат даты", "error")
        return redirect(url_for("ruk.ruk_report"))

    if not reason:
        reason = "Прощение на период"

    db.add_forgiveness_period(target_id, target["fio"], target["role"],
                              start_fmt, end_fmt, reason)
    flash(f"Прощение для {target['fio']} добавлено ({start_fmt} — {end_fmt})", "success")
    return redirect(url_for("ruk.ruk_report"))


@ruk_bp.route("/ruk_delete_forgiveness/<int:forgiveness_id>")
def ruk_delete_forgiveness(forgiveness_id):
    user = get_current_user()
    managed = get_managed_practice(user)
    if managed is None:
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar.calendar_view"))

    conn = db._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM forgiveness WHERE id = ?", (forgiveness_id,))
    forgiveness = cursor.fetchone()

    if not forgiveness:
        flash("Прощение не найдено", "error")
        return redirect(url_for("ruk.ruk_report"))

    if managed != "ALL" and forgiveness["practice"] != managed:
        flash("Можно удалять прощения только студентов своей практики", "error")
        return redirect(url_for("ruk.ruk_report"))

    db.delete_forgiveness(forgiveness_id)
    flash("Прощение удалено", "success")
    return redirect(url_for("ruk.ruk_report"))


@ruk_bp.route("/ruk_toggle_perm_exempt/<user_id>")
def ruk_toggle_perm_exempt(user_id):
    user = get_current_user()
    managed = get_managed_practice(user)
    if managed is None:
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar.calendar_view"))

    target = db.get_user_by_id(user_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("ruk.ruk_report"))

    if managed != "ALL" and target["role"] != managed:
        flash(f"Можно выдавать вечное освобождение только студентам практики {managed}", "error")
        return redirect(url_for("ruk.ruk_report"))

    result = db.toggle_perm_exempt(user_id)
    flash("Вечное освобождение выдано" if result else "Вечное освобождение снято", "success")
    return redirect(url_for("ruk.ruk_report"))