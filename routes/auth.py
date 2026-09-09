"""Аутентификация: вход, регистрация, выход"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import db
from config import PRACTICES, MIN_PASSWORD_LENGTH
from helpers import get_current_user, check_user_reminders

auth_bp = Blueprint('auth', __name__)


@auth_bp.route("/")
def index():
    user = get_current_user()
    if user:
        return redirect(url_for("calendar.calendar_view"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
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
            return redirect(url_for("calendar.calendar_view"))
        else:
            flash(error, "error")

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
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
            return redirect(url_for("auth.login"))
        else:
            flash(msg, "error")

    return render_template("register.html", practices=PRACTICES)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))