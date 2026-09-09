"""Регистрация всех блюпринтов в приложении"""
from .auth import auth_bp
from .calendar import calendar_bp
from .stats import stats_bp
from .profile import profile_bp
from .admin import admin_bp
from .ruk import ruk_bp
from .checkin import checkin_bp


def register_blueprints(app):
    """Регистрирует все блюпринты в Flask-приложении"""
    app.register_blueprint(auth_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ruk_bp)
    app.register_blueprint(checkin_bp)