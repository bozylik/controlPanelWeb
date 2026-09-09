"""Отметка прихода на смену"""
from flask import Blueprint, redirect, url_for, flash
from database import db
from helpers import get_current_user, MSK
from datetime import datetime

checkin_bp = Blueprint('checkin', __name__)


@checkin_bp.route("/checkin/<date_str>/<int:slot>", methods=["POST"])
def checkin(date_str, slot):
    """Отмечает приход студента на смену"""
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))

    # Проверка: пользователь должен быть записан на этот слот
    day_data = db.get_day_data(date_str)
    if slot >= len(day_data) or day_data[slot].strip() != user["fio"]:
        flash("Вы не записаны на это место", "error")
        return redirect(url_for("calendar.day_view", date_str=date_str))

    # Проверка: сейчас должно быть окно чек-ина
    status = db.get_shift_status(date_str, slot)
    if status != "can_checkin":
        flash("Сейчас нельзя отметить приход", "error")
        return redirect(url_for("calendar.day_view", date_str=date_str))

    # Записываем факт прихода
    checkin_time = datetime.now(MSK).strftime("%H:%M")
    success, msg = db.checkin(user["id"], user["fio"], date_str, slot, checkin_time)
    flash(msg, "success" if success else "error")
    return redirect(url_for("calendar.day_view", date_str=date_str))