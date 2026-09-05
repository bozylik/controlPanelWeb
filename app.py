from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from database import db
from config import SECRET_KEY, PRACTICES, EXEMPT_MONTHS, MONTH_NAMES, MONTH_NAMES_GEN, MIN_PASSWORD_LENGTH
import calendar as cal_module
from datetime import datetime, timedelta, timezone
import csv
import io

MSK = timezone(timedelta(hours=3))

app = Flask(__name__)
app.secret_key = SECRET_KEY


def is_admin(role):
    return role.lower() in ['admin', 'админ']


def is_ruk(role):
    return role.lower().startswith("рук")


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


# ==================== ГЛАВНАЯ ====================
@app.route("/")
def index():
    user = get_current_user()
    if user:
        return redirect(url_for("calendar_view"))
    return redirect(url_for("login"))


# ==================== ВХОД ====================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        user, error = db.login_user(username, password)
        if user:
            session["user_id"] = user["user_id"]
            for msg in check_user_reminders(user):
                flash(msg, "info")
            flash(f"Добро пожаловать, {user['fio']}!", "success")
            return redirect(url_for("calendar_view"))
        else:
            flash(error, "error")

    return render_template("login.html")


# ==================== РЕГИСТРАЦИЯ ====================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        password_confirm = request.form.get("password_confirm", "").strip()
        fio = request.form.get("fio", "").strip()
        role_type = request.form.get("role_type", "").strip()
        practice = request.form.get("practice", "").strip()

        if not username or not password or not fio:
            flash("Заполните все обязательные поля", "error")
            return render_template("register.html", practices=PRACTICES)

        if len(username) < 3:
            flash("Логин должен быть минимум 3 символа", "error")
            return render_template("register.html", practices=PRACTICES)

        if len(password) < MIN_PASSWORD_LENGTH:
            flash(f"Пароль должен быть минимум {MIN_PASSWORD_LENGTH} символов", "error")
            return render_template("register.html", practices=PRACTICES)

        if password != password_confirm:
            flash("Пароли не совпадают", "error")
            return render_template("register.html", practices=PRACTICES)

        if practice not in PRACTICES:
            flash("Выберите практику", "error")
            return render_template("register.html", practices=PRACTICES)

        if role_type == "student":
            role = practice
        elif role_type == "ruk":
            role = f"Рук {practice}"
        else:
            flash("Выберите статус", "error")
            return render_template("register.html", practices=PRACTICES)

        success, msg = db.register_user(username, password, fio, role)

        if success:
            flash("Регистрация отправлена. Ожидайте подтверждения администратора.", "success")
            return redirect(url_for("login"))
        else:
            flash(msg, "error")

    return render_template("register.html", practices=PRACTICES)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ==================== КАЛЕНДАРЬ ====================
@app.route("/calendar")
@app.route("/calendar/<int:year>/<int:month>")
def calendar_view(year=None, month=None):
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    now = datetime.now(MSK)
    if year is None: year = now.year
    if month is None: month = now.month

    schedule_data = db.get_schedule_data_for_calendar()
    today = now.date()  # Добавляем текущую дату

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
                # Проверяем, прошёл ли день
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


# ==================== ДЕНЬ ====================
@app.route("/day/<date_str>")
def day_view(date_str):
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    try:
        day_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        today = datetime.now(MSK).date()
        is_past = day_date < today
    except:
        is_past = False

    day_data = db.get_day_data(date_str)

    # Добавляем статусы смен и чек-ины
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


@app.route("/book/<date_str>/<int:slot>")
def book_slot(date_str, slot):
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    # Защита: админ не может записываться
    if is_admin(user["role"]):
        flash("Администратор не может записываться на дежурства", "error")
        return redirect(url_for("day_view", date_str=date_str))

    try:
        booking_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        today = datetime.now(MSK).date()
        if booking_date < today:
            flash("Нельзя записаться на прошедший день", "error")
            return redirect(url_for("calendar_view"))
    except:
        flash("Некорректная дата", "error")
        return redirect(url_for("calendar_view"))

    # Защита: нельзя занять уже занятое место
    day_data = db.get_day_data(date_str)
    if day_data[slot].strip():
        flash("Это место уже занято", "error")
        return redirect(url_for("day_view", date_str=date_str))

    if db.book_slot(date_str, slot, user["fio"]):
        shift_name = "1 смена" if slot < 2 else "2 смена"
        flash(f"Вы записаны на {date_str}, {shift_name}, место {slot + 1}!", "success")
    else:
        flash("Ошибка при бронировании", "error")
    return redirect(url_for("day_view", date_str=date_str))


@app.route("/unbook/<date_str>/<int:slot>")
def unbook_slot(date_str, slot):
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))
    day_data = db.get_day_data(date_str)
    if day_data[slot].strip() == user["fio"] or is_admin(user["role"]):
        db.clear_slot(date_str, slot)
        flash("Запись удалена", "success")
    else:
        flash("Вы можете удалить только свою запись", "error")
    return redirect(url_for("day_view", date_str=date_str))


# ==================== ОТМЕНА ДЕЖУРСТВА ====================
@app.route("/cancel_duty", methods=["GET", "POST"])
def cancel_duty():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

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
            return redirect(url_for("calendar_view"))

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


# ==================== СТАТИСТИКА ====================
@app.route("/stats")
def stats():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    now_msk = datetime.now(MSK)
    today = now_msk.date()

    all_schedule = db.get_all_schedule()
    all_cancels = db.get_all_cancels()
    user_checkins = db.get_user_checkins(user["id"])

    # Словарь чек-инов для быстрого доступа: (дата, слот) → чек-ин
    checkins_dict = {
        (c["date_str"], c["slot"]): c
        for c in user_checkins
    }

    # ==================== ДЕЖУРСТВА ====================
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

                # Определяем статус явки
                checkin = checkins_dict.get((date_str, slot_index))
                if checkin:
                    checkin_status = "present"
                    checkin_time = checkin["checkin_time"]
                elif is_past:
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

    # Сортируем по дате (новые сверху)
    user_shifts.sort(key=lambda x: x["date"], reverse=True)

    # ==================== СТАТИСТИКА ЯВКИ ====================
    present_count = sum(1 for s in user_shifts if s["checkin_status"] == "present")
    missed_count = sum(1 for s in user_shifts if s["checkin_status"] == "missed")
    completed = present_count + missed_count
    attendance_rate = round(present_count / completed * 100, 1) if completed > 0 else 0

    # ==================== ОТМЕНЫ И ОСВОБОЖДЕНИЯ ====================
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

    # ==================== ПРОПУСКИ ПО МЕСЯЦАМ ====================
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

    # ==================== ЗАПРОСЫ НА ОТМЕНУ ====================
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


# ==================== ПРОФИЛЬ ====================
@app.route("/profile")
def profile():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))
    return render_template("profile.html", user=user)


@app.route("/change_password", methods=["POST"])
def change_password():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    old_password = request.form.get("old_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if len(new_password) < MIN_PASSWORD_LENGTH:
        flash(f"Пароль должен быть минимум {MIN_PASSWORD_LENGTH} символов", "error")
        return redirect(url_for("profile"))

    if new_password != confirm_password:
        flash("Новые пароли не совпадают", "error")
        return redirect(url_for("profile"))

    success, msg = db.change_password(user["id"], old_password, new_password)
    flash(msg, "success" if success else "error")
    return redirect(url_for("profile"))


@app.route("/update_profile", methods=["POST"])
def update_profile():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    new_fio = request.form.get("fio", "").strip()
    if new_fio:
        db.update_user_profile(user["id"], new_fio=new_fio)
        flash("Профиль обновлён", "success")
    return redirect(url_for("profile"))


# ==================== АДМИН-ПАНЕЛЬ ====================
@app.route("/admin")
def admin_panel():
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar_view"))

    all_users = db.get_all_users()

    # Счётчики
    students = [u for u in all_users if u["role"] in PRACTICES]
    ruks = [u for u in all_users if u["role"].startswith("Рук")]
    admins = [u for u in all_users if is_admin(u["role"])]
    pending_users = [u for u in all_users if u["approval_status"] == "pending"]

    # Сводка в виде карточек
    summary_cards = db.get_summary_cards()
    filter_practice = request.args.get("practice", "all")

    # Активные освобождения на период
    active_exemptions = db.get_active_exemptions()

    return render_template(
        "admin.html",
        user=user,
        students=students,
        summary_cards=summary_cards,
        filter_practice=filter_practice,
        practices=PRACTICES,
        total_students=len(students),
        total_ruks=len(ruks),
        total_admins=len(admins),
        total_pending=len(pending_users),
        total_shifts=len(db.get_all_schedule()) - 1,
        total_cancels=len(db.get_all_cancels()) - 1,
        active_exemptions=active_exemptions,
        MONTH_NAMES=MONTH_NAMES
    )


@app.route("/admin/summary.csv")
def export_summary_csv():
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar_view"))

    summary = db.get_summary_data()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(summary["headers"])
    for row in summary["all"]:
        writer.writerow(row)

    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=summary.csv'}
    )


@app.route("/admin/toggle_exempt/<user_id>")
def toggle_exempt(user_id):
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar_view"))
    result = db.toggle_perm_exempt(user_id)
    flash("Вечное освобождение выдано" if result else "Вечное освобождение снято", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/delete_user/<user_id>")
def delete_user(user_id):
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar_view"))

    # Защита: нельзя удалить самого себя
    if user["id"] == user_id:
        flash("Нельзя удалить самого себя!", "error")
        return redirect(url_for("admin_users"))

    db.delete_user(user_id)
    flash("Пользователь удалён", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/forgive", methods=["POST"])
def forgive_duty():
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar_view"))

    target_id = request.form.get("target_id")
    month = int(request.form.get("month", 0))
    year = int(request.form.get("year", 0))
    reason = request.form.get("reason", "").strip()

    if target_id and month and year and reason:
        target = db.get_user_by_id(target_id)
        if target:
            now = datetime.now(MSK)
            fake_date = f"Освобождение {month:02d}.{year}"
            practice = db.get_user_practice(target_id)
            db.add_cancel(target["fio"], practice, now.strftime("%d.%m.%Y"), fake_date, reason)
            flash(f"{target['fio']} прощен за {MONTH_NAMES[month - 1]} {year}", "success")
    return redirect(url_for("admin_panel"))


# ==================== АДМИН-ПАНЕЛЬ ПОЛЬЗОВАТЕЛЕЙ ====================
@app.route("/admin/users")
def admin_users():
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar_view"))

    all_users = db.get_all_users()
    pending_users = [u for u in all_users if u["approval_status"] == "pending"]
    approved_users = [u for u in all_users if u["approval_status"] == "approved"]
    rejected_users = [u for u in all_users if u["approval_status"] == "rejected"]

    return render_template(
        "admin_users.html",
        user=user,
        all_users=all_users,
        pending_users=pending_users,
        approved_users=approved_users,
        rejected_users=rejected_users,
        practices=PRACTICES  # ← ДОБАВЬ ЭТУ СТРОКУ
    )


@app.route("/admin/toggle_active/<user_id>")
def toggle_active(user_id):
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar_view"))

    # Защита: нельзя заблокировать самого себя
    if user["id"] == user_id:
        flash("Нельзя заблокировать самого себя!", "error")
        return redirect(url_for("admin_users"))

    result = db.toggle_user_active(user_id)
    if result is not None:
        flash("Пользователь разблокирован" if result else "Пользователь заблокирован", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/reset_password/<user_id>", methods=["POST"])
def admin_reset_password(user_id):
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar_view"))

    new_password = request.form.get("new_password", "").strip()
    if len(new_password) < MIN_PASSWORD_LENGTH:
        flash(f"Пароль должен быть минимум {MIN_PASSWORD_LENGTH} символов", "error")
        return redirect(url_for("admin_users"))

    db.reset_password_by_admin(user_id, new_password)
    flash("Пароль пользователя сброшен", "success")
    return redirect(url_for("admin_users"))


# ==================== ОТЧЁТ РУКОВОДИТЕЛЯ ====================
@app.route("/ruk_report")
@app.route("/ruk_report/<int:month>/<int:year>")
def ruk_report(month=None, year=None):
    user = get_current_user()
    if not user or not is_ruk(user["role"]):
        return redirect(url_for("calendar_view"))

    now = datetime.now(MSK)
    if month is None: month = now.month
    if year is None: year = now.year

    target_p = user["role"][4:].strip()
    all_users = db.get_all_users()
    all_schedule = db.get_all_schedule()
    all_cancels = db.get_all_cancels()

    # Все освобождения текущего месяца (legacy-формат из cancels)
    forgiven_this_month = {}
    target_str = f"Освобождение {month:02d}.{year}"
    for r in all_cancels[1:]:
        if len(r) >= 5 and r[3].strip() == target_str:
            forgiven_this_month[r[0].strip()] = r[4].strip()

    # Все отмены (для истории)
    all_cancels_by_fio = {}
    for r in all_cancels[1:]:
        if len(r) >= 5:
            fio = r[0].strip()
            if fio not in all_cancels_by_fio:
                all_cancels_by_fio[fio] = []
            all_cancels_by_fio[fio].append({
                "cancel_date": r[2].strip(),
                "target": r[3].strip(),
                "reason": r[4].strip()
            })

    # Все чек-ины за выбранный месяц
    target_m_str = f".{month:02d}.{year}"
    checkins_by_fio = {}
    conn = db._get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM checkins WHERE date_str LIKE ?",
        (f'%{target_m_str}',)
    )
    for row in cursor.fetchall():
        row_dict = dict(row)
        fio = row_dict["fio"]
        if fio not in checkins_by_fio:
            checkins_by_fio[fio] = []
        checkins_by_fio[fio].append(row_dict)

    # ✅ Активные прощения своей практики — вычисляем ДО цикла
    all_active_forgiveness = db.get_active_forgiveness()
    # ✅ Все прощения практики, пересекающиеся с выбранным месяцем
    all_forgiveness = db.get_all_forgiveness_by_practice(target_p)

    # Границы выбранного месяца
    month_start = datetime(year, month, 1).date()
    if month == 12:
        month_end = datetime(year, 12, 31).date()
    else:
        month_end = datetime(year, month + 1, 1).date() - timedelta(days=1)

    # Фильтруем: прощение попадает в месяц, если пересекается с ним
    active_forgiveness_my = []
    for f in all_forgiveness:
        try:
            f_start = datetime.strptime(f["start_date"], "%d.%m.%Y").date()
            f_end = datetime.strptime(f["end_date"], "%d.%m.%Y").date()
            # Пересечение периодов: start <= month_end И end >= month_start
            if f_start <= month_end and f_end >= month_start:
                active_forgiveness_my.append(f)
        except (ValueError, KeyError):
            continue

    # Предварительно парсим периоды прощений для быстрой проверки
    forgiveness_periods = []
    for f in active_forgiveness_my:
        try:
            f_start = datetime.strptime(f["start_date"], "%d.%m.%Y").date()
            f_end = datetime.strptime(f["end_date"], "%d.%m.%Y").date()
            forgiveness_periods.append((f["fio"], f_start, f_end))
        except (ValueError, KeyError):
            pass

    def is_date_forgiven(person_fio, shift_date):
        """Проверяет, попадает ли дата в прощённый период студента"""
        for f_fio, f_start, f_end in forgiveness_periods:
            if f_fio == person_fio and f_start <= shift_date <= f_end:
                return True
        return False

    # Статистика по отчёту
    total_students = 0
    active_students = 0
    lazy_students = 0
    exempt_students = 0

    # Общая статистика явки по практике
    practice_present = 0
    practice_missed = 0

    students = []
    for u in all_users:
        if u["role"] == target_p:
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
                # Статистика явки
                "present_count": 0,
                "missed_count": 0,
                "forgiven_count": 0,
                "attendance_rate": 0,
            }

            if is_perm:
                student_data["status"] = "exempt"
                exempt_students += 1
            elif student_data["forgiven_this_month"]:
                student_data["status"] = "forgiven"
                exempt_students += 1
            else:
                # Записи на дежурства в этом месяце
                for s in all_schedule[1:]:
                    if len(s) >= 2 and target_m_str in s[0]:
                        row_fios = [f.strip() for f in s[1:5]]
                        for slot_index, fio_in_slot in enumerate(row_fios):
                            if fio_in_slot == fio:
                                shift_name = "1 смена (10:00-12:00)" if slot_index < 2 else "2 смена (13:00-16:00)"

                                # Проверяем чек-ин
                                date_str = s[0].strip()
                                checkin = None
                                for c in checkins_by_fio.get(fio, []):
                                    if c["date_str"] == date_str and c["slot"] == slot_index:
                                        checkin = c
                                        break

                                # Определяем, прошла ли смена
                                try:
                                    shift_date = datetime.strptime(date_str, "%d.%m.%Y").date()
                                    is_past = shift_date < now.date()
                                except ValueError:
                                    is_past = False

                                # ✅ Определяем статус явки с учётом прощений
                                if checkin:
                                    checkin_status = "present"
                                    checkin_time = checkin["checkin_time"]
                                    student_data["present_count"] += 1
                                    practice_present += 1
                                elif is_past and is_date_forgiven(fio, shift_date):
                                    # Неявка прощена — не считается в статистике
                                    checkin_status = "forgiven"
                                    checkin_time = None
                                    student_data["forgiven_count"] += 1
                                elif is_past:
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

                # Подсчёт процента явки (прощённые неявки НЕ учитываются)
                completed = student_data["present_count"] + student_data["missed_count"]
                if completed > 0:
                    student_data["attendance_rate"] = round(
                        student_data["present_count"] / completed * 100, 1
                    )
                elif student_data["forgiven_count"] > 0:
                    # Все завершённые смены прощены — явка 100%
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

    # Активные освобождения
    all_active_exemptions = db.get_active_exemptions()
    my_students_fios = {s["fio"] for s in students}
    active_exemptions_my = [e for e in all_active_exemptions if e["fio"] in my_students_fios]

    # Запросы на отмену
    pending_cancel_requests = db.get_ruk_cancel_requests(target_p)

    # Общая статистика явки по практике
    practice_completed = practice_present + practice_missed
    practice_attendance_rate = round(
        practice_present / practice_completed * 100, 1
    ) if practice_completed > 0 else 0

    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1

    return render_template("ruk_report.html",
                           user=user,
                           students=students,
                           target_p=target_p,
                           month_name=MONTH_NAMES[month - 1],
                           year=year,
                           month=month,
                           prev_m=prev_m, prev_y=prev_y,
                           next_m=next_m, next_y=next_y,
                           total_students=total_students,
                           active_students=active_students,
                           lazy_students=lazy_students,
                           exempt_students=exempt_students,
                           active_exemptions=active_exemptions_my,
                           pending_cancel_requests=pending_cancel_requests,
                           active_forgiveness=active_forgiveness_my,
                           practice_present=practice_present,
                           practice_missed=practice_missed,
                           practice_attendance_rate=practice_attendance_rate)


@app.route("/ruk_delete_student/<user_id>")
def ruk_delete_student(user_id):
    user = get_current_user()

    # Только руководители могут удалять
    if not user or not is_ruk(user["role"]):
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar_view"))

    # Защита: нельзя удалить себя
    if user["id"] == user_id:
        flash("Нельзя удалить самого себя", "error")
        return redirect(url_for("ruk_report"))

    target = db.get_user_by_id(user_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("ruk_report"))

    # Защита: нельзя удалить админа или другого руководителя
    if is_admin(target["role"]) or is_ruk(target["role"]):
        flash("Нельзя удалить администратора или руководителя", "error")
        return redirect(url_for("ruk_report"))

    # Проверка: студент должен быть из той же практики
    ruk_practice = user["role"][4:].strip()  # "Рук ГП" → "ГП"
    if target["role"] != ruk_practice:
        flash(f"Можно удалять только студентов практики {ruk_practice}", "error")
        return redirect(url_for("ruk_report"))

    # Удаляем аккаунт и чистим записи в расписании
    db.delete_user_and_clean_schedule(user_id, target["fio"])
    flash(f"Студент {target['fio']} удалён", "success")
    return redirect(url_for("ruk_report"))


@app.route("/ruk_remove_shift/<date_str>/<int:slot>", methods=["POST"])
def ruk_remove_shift(date_str, slot):
    """Руководитель удаляет запись только БУДУЩЕЙ смены"""
    user = get_current_user()
    if not user or not is_ruk(user["role"]):
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar_view"))

    ruk_practice = user["role"][4:].strip()

    # Проверяем, что место занято
    day_data = db.get_day_data(date_str)
    if slot >= len(day_data) or not day_data[slot].strip():
        flash("Это место уже свободно", "error")
        return redirect(url_for("ruk_report"))

    # ✅ НОВОЕ: завершённую смену удалить нельзя
    status = db.get_shift_status(date_str, slot)
    if status in ["past", "missed"]:
        flash("Эта смена уже завершена. Факт явки/неявки неизменяем. "
              "Используйте прощение, чтобы снять отметку 'не явился'.", "error")
        return redirect(url_for("ruk_report"))

    target_fio = day_data[slot].strip()

    # Ищем студента по ФИО
    all_users = db.get_all_users()
    target = None
    for u in all_users:
        if u["fio"] == target_fio:
            target = u
            break

    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("ruk_report"))

    # Защита: только студенты СВОЕЙ практики
    if target["role"] != ruk_practice:
        flash(f"Можно удалять записи только студентов практики {ruk_practice}", "error")
        return redirect(url_for("ruk_report"))

    reason = request.form.get("reason", "").strip()
    if reason:
        full_reason = f"{reason} (удалено руководителем {ruk_practice})"
    else:
        full_reason = f"Удалено руководителем {ruk_practice}"

    db.clear_slot(date_str, slot)
    db.add_cancel(
        target_fio,
        target["role"],
        datetime.now(MSK).strftime("%d.%m.%Y"),
        date_str,
        full_reason
    )

    flash(f"Запись {target_fio} на {date_str} удалена", "success")
    return redirect(url_for("ruk_report"))


@app.route("/admin/approve_user/<user_id>")
def approve_user(user_id):
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar_view"))

    if user["id"] == user_id:
        flash("Нельзя подтверждать самого себя.", "error")
        return redirect(url_for("admin_users"))

    db.approve_user(user_id)
    flash("Пользователь подтверждён", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/reject_user/<user_id>")
def reject_user(user_id):
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar_view"))

    if user["id"] == user_id:
        flash("Нельзя отклонить самого себя.", "error")
        return redirect(url_for("admin_users"))

    target = db.get_user_by_id(user_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("admin_users"))

    # Удаляем пользователя полностью (чтобы он мог зарегистрироваться заново)
    db.delete_user(user_id)
    flash(f"Пользователь {target['fio']} отклонён и удалён", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/forgive_day", methods=["POST"])
def forgive_day():
    """Прощение дежурства за конкретный день"""
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar_view"))

    target_id = request.form.get("target_id")
    date_str = request.form.get("date", "").strip()
    reason = request.form.get("reason", "").strip()

    if not target_id or not date_str:
        flash("Выберите студента и дату", "error")
        return redirect(url_for("admin_panel"))

    target = db.get_user_by_id(target_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("admin_panel"))

    if not reason:
        reason = "Прощено администратором"

    practice = db.get_user_practice(target_id)
    db.forgive_specific_day(target_id, target["fio"], practice, date_str, reason)

    flash(f"Дежурство {target['fio']} за {date_str} прощено", "success")
    return redirect(url_for("admin_panel"))


@app.route("/ruk_add_exemption", methods=["POST"])
def ruk_add_exemption():
    """Руководитель выдает освобождение на период"""
    user = get_current_user()
    if not user or not is_ruk(user["role"]):
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar_view"))

    target_id = request.form.get("target_id")
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()
    reason = request.form.get("reason", "").strip()

    if not target_id or not start_date or not end_date:
        flash("Заполните все поля", "error")
        return redirect(url_for("ruk_report"))

    target = db.get_user_by_id(target_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("ruk_report"))

    # Защита: только студентов СВОЕЙ практики
    ruk_practice = user["role"][4:].strip()
    if target["role"] != ruk_practice:
        flash(f"Можно выдавать освобождения только студентам практики {ruk_practice}", "error")
        return redirect(url_for("ruk_report"))

    # Проверка дат
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if end_dt < start_dt:
            flash("Дата окончания должна быть позже даты начала", "error")
            return redirect(url_for("ruk_report"))
        start_date_fmt = start_dt.strftime("%d.%m.%Y")
        end_date_fmt = end_dt.strftime("%d.%m.%Y")
    except ValueError:
        flash("Некорректный формат даты", "error")
        return redirect(url_for("ruk_report"))

    if not reason:
        reason = f"Освобождение от руководителя {ruk_practice}"

    db.add_exemption(target_id, target["fio"], start_date_fmt, end_date_fmt, reason)
    flash(f"Освобождение для {target['fio']} добавлено ({start_date_fmt} — {end_date_fmt})", "success")
    return redirect(url_for("ruk_report"))


@app.route("/ruk_delete_exemption/<int:exemption_id>")
def ruk_delete_exemption(exemption_id):
    """Руководитель удаляет освобождение своего студента"""
    user = get_current_user()
    if not user or not is_ruk(user["role"]):
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar_view"))

    ruk_practice = user["role"][4:].strip()

    # Получаем освобождение и проверяем, что студент из его практики
    conn = db._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM exemptions WHERE id = ?", (exemption_id,))
    exemption = cursor.fetchone()

    if not exemption:
        flash("Освобождение не найдено", "error")
        return redirect(url_for("ruk_report"))

    # Находим роль студента
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (exemption["user_id"],))
    user_role_row = cursor.fetchone()

    if not user_role_row or user_role_row["role"] != ruk_practice:
        flash("Можно удалять освобождения только студентов своей практики", "error")
        return redirect(url_for("ruk_report"))

    db.delete_exemption(exemption_id)
    flash("Освобождение удалено", "success")
    return redirect(url_for("ruk_report"))


@app.route("/approve_cancel/<int:request_id>")
def approve_cancel(request_id):
    """Руководитель одобряет запрос на отмену"""
    user = get_current_user()
    if not user or not is_ruk(user["role"]):
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar_view"))

    ruk_practice = user["role"][4:].strip()

    # Проверяем, что запрос от студента своей практики
    conn = db._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cancel_requests WHERE id = ?", (request_id,))
    req = cursor.fetchone()

    if not req or req["practice"] != ruk_practice:
        flash("Можно одобрять только запросы своих студентов", "error")
        return redirect(url_for("ruk_report"))

    result = db.approve_cancel_request(request_id)
    if result:
        flash(f"Запрос {result['fio']} на {result['date_str']} одобрен", "success")
    else:
        flash("Ошибка при одобрении", "error")
    return redirect(url_for("ruk_report"))


@app.route("/reject_cancel/<int:request_id>")
def reject_cancel(request_id):
    """Руководитель отклоняет запрос на отмену"""
    user = get_current_user()
    if not user or not is_ruk(user["role"]):
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar_view"))

    ruk_practice = user["role"][4:].strip()

    conn = db._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cancel_requests WHERE id = ?", (request_id,))
    req = cursor.fetchone()

    if not req or req["practice"] != ruk_practice:
        flash("Можно отклонять только запросы своих студентов", "error")
        return redirect(url_for("ruk_report"))

    result = db.reject_cancel_request(request_id)
    if result:
        flash(f"Запрос {result['fio']} на {result['date_str']} отклонён", "error")
    else:
        flash("Ошибка при отклонении", "error")
    return redirect(url_for("ruk_report"))

@app.route("/admin/add_exemption", methods=["POST"])
def add_exemption():
    """Добавление освобождения на период"""
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar_view"))

    target_id = request.form.get("target_id")
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()
    reason = request.form.get("reason", "").strip()

    if not target_id or not start_date or not end_date:
        flash("Заполните все поля", "error")
        return redirect(url_for("admin_panel"))

    target = db.get_user_by_id(target_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("admin_panel"))

    # Проверка дат
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if end_dt < start_dt:
            flash("Дата окончания должна быть позже даты начала", "error")
            return redirect(url_for("admin_panel"))
        # Конвертируем в формат дд.мм.гггг
        start_date_fmt = start_dt.strftime("%d.%m.%Y")
        end_date_fmt = end_dt.strftime("%d.%m.%Y")
    except ValueError:
        flash("Некорректный формат даты", "error")
        return redirect(url_for("admin_panel"))

    if not reason:
        reason = "Освобождение на период"

    db.add_exemption(target_id, target["fio"], start_date_fmt, end_date_fmt, reason)
    flash(f"Освобождение для {target['fio']} добавлено ({start_date_fmt} — {end_date_fmt})", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/delete_exemption/<int:exemption_id>")
def delete_exemption(exemption_id):
    """Удаление освобождения"""
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar_view"))

    db.delete_exemption(exemption_id)
    flash("Освобождение удалено", "success")
    return redirect(url_for("admin_panel"))

@app.route("/unbook_from_stats/<date_str>", methods=["POST"])
def unbook_from_stats(date_str):
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    # Проверяем, не прошёл ли день
    try:
        day_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        today = datetime.now(MSK).date()
        if day_date < today:
            flash("Нельзя отменить прошедшее дежурство", "error")
            return redirect(url_for("stats"))
    except:
        flash("Некорректная дата", "error")
        return redirect(url_for("stats"))

    reason = request.form.get("reason", "").strip()
    if not reason:
        flash("Укажите причину отмены", "error")
        return redirect(url_for("stats"))

    # Админы отменяют сразу без согласования
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
        return redirect(url_for("stats"))

    # Студенты и руководители создают запрос на согласование
    practice = db.get_user_practice(user["id"])
    success, msg = db.create_cancel_request(
        user["id"], user["fio"], practice, date_str, reason
    )
    flash(msg, "success" if success else "error")
    return redirect(url_for("stats"))


@app.route("/admin/change_role/<user_id>", methods=["POST"])
def change_user_role(user_id):
    """Админ меняет роль пользователя"""
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar_view"))

    # Защита: нельзя менять роль самому себе
    if user["id"] == user_id:
        flash("Нельзя менять роль самому себе", "error")
        return redirect(url_for("admin_users"))

    new_role = request.form.get("new_role", "").strip()

    # Валидация роли
    valid_roles = PRACTICES + \
                  [f"Рук {p}" for p in PRACTICES] + \
                  ["admin"]

    if new_role not in valid_roles:
        flash("Некорректная роль", "error")
        return redirect(url_for("admin_users"))

    target = db.get_user_by_id(user_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("admin_users"))

    old_role = target["role"]
    db.update_user_role(user_id, new_role)
    flash(f"Роль {target['fio']} изменена: {old_role} → {new_role}", "success")
    return redirect(url_for("admin_users"))


@app.route("/ruk_forgive_period", methods=["POST"])
def ruk_forgive_period():
    """Руководитель выдает прощение на период"""
    user = get_current_user()
    if not user or not is_ruk(user["role"]):
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar_view"))

    target_id = request.form.get("target_id")
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()
    reason = request.form.get("reason", "").strip()

    if not target_id or not start_date or not end_date:
        flash("Заполните все поля", "error")
        return redirect(url_for("ruk_report"))

    target = db.get_user_by_id(target_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("ruk_report"))

    ruk_practice = user["role"][4:].strip()
    if target["role"] != ruk_practice:
        flash(f"Можно прощать только студентов практики {ruk_practice}", "error")
        return redirect(url_for("ruk_report"))

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if end_dt < start_dt:
            flash("Дата окончания должна быть позже даты начала", "error")
            return redirect(url_for("ruk_report"))
        start_date_fmt = start_dt.strftime("%d.%m.%Y")
        end_date_fmt = end_dt.strftime("%d.%m.%Y")
    except ValueError:
        flash("Некорректный формат даты", "error")
        return redirect(url_for("ruk_report"))

    if not reason:
        reason = f"Прощение от руководителя {ruk_practice}"

    db.add_forgiveness_period(target_id, target["fio"], target["role"],
                               start_date_fmt, end_date_fmt, reason)
    flash(f"Прощение для {target['fio']} добавлено ({start_date_fmt} — {end_date_fmt})", "success")
    return redirect(url_for("ruk_report"))


@app.route("/ruk_delete_forgiveness/<int:forgiveness_id>")
def ruk_delete_forgiveness(forgiveness_id):
    """Руководитель удаляет прощение своего студента"""
    user = get_current_user()
    if not user or not is_ruk(user["role"]):
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar_view"))

    ruk_practice = user["role"][4:].strip()

    conn = db._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM forgiveness WHERE id = ?", (forgiveness_id,))
    forgiveness = cursor.fetchone()

    if not forgiveness:
        flash("Прощение не найдено", "error")
        return redirect(url_for("ruk_report"))

    if forgiveness["practice"] != ruk_practice:
        flash("Можно удалять прощения только студентов своей практики", "error")
        return redirect(url_for("ruk_report"))

    db.delete_forgiveness(forgiveness_id)
    flash("Прощение удалено", "success")
    return redirect(url_for("ruk_report"))


@app.route("/checkin/<date_str>/<int:slot>", methods=["POST"])
def checkin(date_str, slot):
    """Отметка прихода на смену"""
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    # Проверяем, что пользователь записан на этот слот
    day_data = db.get_day_data(date_str)
    if slot >= len(day_data) or day_data[slot].strip() != user["fio"]:
        flash("Вы не записаны на это место", "error")
        return redirect(url_for("day_view", date_str=date_str))

    # Проверяем статус смены
    status = db.get_shift_status(date_str, slot)
    if status not in ["can_checkin"]:
        flash("Сейчас нельзя отметить приход", "error")
        return redirect(url_for("day_view", date_str=date_str))

    checkin_time = datetime.now(MSK).strftime("%H:%M")
    success, msg = db.checkin(user["id"], user["fio"], date_str, slot, checkin_time)
    flash(msg, "success" if success else "error")
    return redirect(url_for("day_view", date_str=date_str))

@app.route("/ruk_toggle_perm_exempt/<user_id>")
def ruk_toggle_perm_exempt(user_id):
    """Руководитель выдает/снимает вечное освобождение"""
    user = get_current_user()
    if not user or not is_ruk(user["role"]):
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar_view"))

    ruk_practice = user["role"][4:].strip()

    target = db.get_user_by_id(user_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("ruk_report"))

    if target["role"] != ruk_practice:
        flash(f"Можно выдавать вечное освобождение только студентам практики {ruk_practice}", "error")
        return redirect(url_for("ruk_report"))

    result = db.toggle_perm_exempt(user_id)
    if result:
        flash(f"Вечное освобождение выдано: {target['fio']}", "success")
    else:
        flash(f"Вечное освобождение снято: {target['fio']}", "success")
    return redirect(url_for("ruk_report"))


# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    print("Инициализация базы данных...")
    db.init()
    print("Запуск сервера на http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)