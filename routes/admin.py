"""Админ-панель"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from database import db
from config import PRACTICES, MONTH_NAMES, MIN_PASSWORD_LENGTH
from helpers import get_current_user, is_admin, MSK
from datetime import datetime
import csv
import io

admin_bp = Blueprint('admin', __name__)


@admin_bp.route("/admin")
def admin_panel():
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar.calendar_view"))

    all_users = db.get_all_users()

    students = [u for u in all_users if u["role"] in PRACTICES]
    ruks = [u for u in all_users if u["role"].startswith("Рук")]
    admins = [u for u in all_users if is_admin(u["role"])]
    pending_users = [u for u in all_users if u["approval_status"] == "pending"]

    summary_cards = db.get_summary_cards()
    filter_practice = request.args.get("practice", "all")

    active_exemptions = db.get_active_exemptions()

    return render_template(
        "admin.html",
        user=user,
        students=students,
        summary_cards=summary_cards,
        filter_practice=filter_practice,
        practices=PRACTICES,
        pending_users=pending_users,
        total_students=len(students),
        total_ruks=len(ruks),
        total_admins=len(admins),
        total_pending=len(pending_users),
        total_shifts=len(db.get_all_schedule()) - 1,
        total_cancels=len(db.get_all_cancels()) - 1,
        active_exemptions=active_exemptions,
        MONTH_NAMES=MONTH_NAMES
    )


@admin_bp.route("/admin/summary.csv")
def export_summary_csv():
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar.calendar_view"))

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


@admin_bp.route("/admin/toggle_exempt/<user_id>")
def toggle_exempt(user_id):
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar.calendar_view"))
    result = db.toggle_perm_exempt(user_id)
    flash("Вечное освобождение выдано" if result else "Вечное освобождение снято", "success")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/admin/delete_user/<user_id>")
def delete_user(user_id):
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar.calendar_view"))

    if user["id"] == user_id:
        flash("Нельзя удалить самого себя!", "error")
        return redirect(url_for("admin.admin_users"))

    db.delete_user(user_id)
    flash("Пользователь удалён", "success")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/admin/forgive", methods=["POST"])
def forgive_duty():
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar.calendar_view"))

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
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/admin/users")
def admin_users():
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar.calendar_view"))

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
        practices=PRACTICES
    )


@admin_bp.route("/admin/toggle_active/<user_id>")
def toggle_active(user_id):
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar.calendar_view"))

    if user["id"] == user_id:
        flash("Нельзя заблокировать самого себя!", "error")
        return redirect(url_for("admin.admin_users"))

    result = db.toggle_user_active(user_id)
    if result is not None:
        flash("Пользователь разблокирован" if result else "Пользователь заблокирован", "success")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/admin/reset_password/<user_id>", methods=["POST"])
def admin_reset_password(user_id):
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar.calendar_view"))

    new_password = request.form.get("new_password", "").strip()
    if len(new_password) < MIN_PASSWORD_LENGTH:
        flash(f"Пароль должен быть минимум {MIN_PASSWORD_LENGTH} символов", "error")
        return redirect(url_for("admin.admin_users"))

    db.reset_password_by_admin(user_id, new_password)
    flash("Пароль пользователя сброшен", "success")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/admin/approve_user/<user_id>")
def approve_user(user_id):
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar.calendar_view"))

    if user["id"] == user_id:
        flash("Нельзя подтверждать самого себя.", "error")
        return redirect(url_for("admin.admin_users"))

    db.approve_user(user_id)
    flash("Пользователь подтверждён", "success")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/admin/reject_user/<user_id>")
def reject_user(user_id):
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar.calendar_view"))

    if user["id"] == user_id:
        flash("Нельзя отклонить самого себя.", "error")
        return redirect(url_for("admin.admin_users"))

    target = db.get_user_by_id(user_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("admin.admin_users"))

    db.delete_user(user_id)
    flash(f"Пользователь {target['fio']} отклонён и удалён", "success")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/admin/forgive_day", methods=["POST"])
def forgive_day():
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar.calendar_view"))

    target_id = request.form.get("target_id")
    date_str = request.form.get("date", "").strip()
    reason = request.form.get("reason", "").strip()

    if not target_id or not date_str:
        flash("Выберите студента и дату", "error")
        return redirect(url_for("admin.admin_panel"))

    target = db.get_user_by_id(target_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("admin.admin_panel"))

    if not reason:
        reason = "Прощено администратором"

    practice = db.get_user_practice(target_id)
    db.forgive_specific_day(target_id, target["fio"], practice, date_str, reason)

    flash(f"Дежурство {target['fio']} за {date_str} прощено", "success")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/admin/add_exemption", methods=["POST"])
def add_exemption():
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar.calendar_view"))

    target_id = request.form.get("target_id")
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()
    reason = request.form.get("reason", "").strip()

    if not target_id or not start_date or not end_date:
        flash("Заполните все поля", "error")
        return redirect(url_for("admin.admin_panel"))

    target = db.get_user_by_id(target_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("admin.admin_panel"))

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        if end_dt < start_dt:
            flash("Дата окончания должна быть позже даты начала", "error")
            return redirect(url_for("admin.admin_panel"))
        start_date_fmt = start_dt.strftime("%d.%m.%Y")
        end_date_fmt = end_dt.strftime("%d.%m.%Y")
    except ValueError:
        flash("Некорректный формат даты", "error")
        return redirect(url_for("admin.admin_panel"))

    if not reason:
        reason = "Освобождение на период"

    db.add_exemption(target_id, target["fio"], start_date_fmt, end_date_fmt, reason)
    flash(f"Освобождение для {target['fio']} добавлено ({start_date_fmt} — {end_date_fmt})", "success")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/admin/delete_exemption/<int:exemption_id>")
def delete_exemption(exemption_id):
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        return redirect(url_for("calendar.calendar_view"))

    db.delete_exemption(exemption_id)
    flash("Освобождение удалено", "success")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/admin/change_role/<user_id>", methods=["POST"])
def change_user_role(user_id):
    user = get_current_user()
    if not user or not is_admin(user["role"]):
        flash("Недостаточно прав", "error")
        return redirect(url_for("calendar.calendar_view"))

    if user["id"] == user_id:
        flash("Нельзя менять роль самому себе", "error")
        return redirect(url_for("admin.admin_users"))

    new_role = request.form.get("new_role", "").strip()

    valid_roles = PRACTICES + [f"Рук {p}" for p in PRACTICES] + ["admin"]

    if new_role not in valid_roles:
        flash("Некорректная роль", "error")
        return redirect(url_for("admin.admin_users"))

    target = db.get_user_by_id(user_id)
    if not target:
        flash("Пользователь не найден", "error")
        return redirect(url_for("admin.admin_users"))

    old_role = target["role"]
    db.update_user_role(user_id, new_role)
    flash(f"Роль {target['fio']} изменена: {old_role} → {new_role}", "success")
    return redirect(url_for("admin.admin_users"))