# config.py
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
MIN_PASSWORD_LENGTH = 6

# ✅ Только из переменных окружения
TURSO_DATABASE_URL = "libsql://duty-korovoy.aws-eu-west-1.turso.io"
TURSO_AUTH_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODg5NTM3MzUsImlkIjoiMDFhMDg1ZTItOTYwMS03ZTA1LTk2MzYtYzQ5ZGE2YjUzMTIxIiwia2lkIjoiNEtEYWVCczM3bWp2T2VKWnhHN0hhYWNfa2xOMnY1UFNOSU40YXFxamNaQSIsInJpZCI6IjU5MGVmNTExLWFkYWQtNGMxYi1hMDYyLWQ1N2YzOWU4NjAxNiJ9.Nyx86VLWXMdUeZlSG6PzNV7YxHvd_yLOKqzkaHISd9R8EKr7fO33aiLyaIH6VRiee2ou_mu7UFhm8pxj3viaAA"


DB_PATH = str(BASE_DIR / "duty.db")

PRACTICES = ["ГП", "АП", "СП"]
EXEMPT_MONTHS = [7, 8]
MONTH_NAMES = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
               "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
MONTH_NAMES_GEN = ["Января", "Февраля", "Марта", "Апреля", "Мая", "Июня",
                   "Июля", "Августа", "Сентября", "Октября", "Ноября", "Декабря"]