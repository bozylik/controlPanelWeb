import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
MIN_PASSWORD_LENGTH = 6

# Если есть TURSO — используем его, иначе локальный файл
TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

# Локальный путь — только для разработки без Turso
DB_PATH = str(BASE_DIR / "duty.db")

PRACTICES = ["ГП", "АП", "СП"]  # ← подставь свои
EXEMPT_MONTHS = [7, 8]
MONTH_NAMES = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
               "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
MONTH_NAMES_GEN = ["Января", "Февраля", "Марта", "Апреля", "Мая", "Июня",
                   "Июля", "Августа", "Сентября", "Октября", "Ноября", "Декабря"]