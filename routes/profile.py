"""Профиль пользователя"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import db
from config import MIN_PASSWORD_LENGTH
from helpers import get_current_user

profile_bp = Blueprint('profile', __name__)


@profile_bp.route("/profile")
def profile():
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))
    return render_template("profile.html", user=user)


@profile_bp.route("/change_password", methods=["POST"])
def change_password():
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))

    old_password = request.form.get("old_password") or ""
    new_password = request.form.get("new_password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    if not old_password:
        flash("Введите текущий пароль", "error")
        return redirect(url_for("profile.profile"))

    if len(new_password) < MIN_PASSWORD_LENGTH:
        flash(f"Пароль должен быть минимум {MIN_PASSWORD_LENGTH} символов", "error")
        return redirect(url_for("profile.profile"))

    if new_password != confirm_password:
        flash("Новые пароли не совпадают", "error")
        return redirect(url_for("profile.profile"))

    if new_password == old_password:
        flash("Новый пароль совпадает с текущим", "error")
        return redirect(url_for("profile.profile"))

    # Защищено от падений: любое исключение превращается в понятную ошибку
    try:
        success, msg = db.change_password(user["id"], old_password, new_password)
    except Exception as e:
        success, msg = False, f"Ошибка при смене пароля: {e}"

    flash(msg, "success" if success else "error")
    return redirect(url_for("profile.profile"))


@profile_bp.route("/update_profile", methods=["POST"])
def update_profile():
    user = get_current_user()
    if not user:
        return redirect(url_for("auth.login"))

    new_fio = request.form.get("fio", "").strip()
    if new_fio:
        db.update_user_profile(user["id"], new_fio=new_fio)
        flash("Профиль обновлён", "success")
    return redirect(url_for("profile.profile"))