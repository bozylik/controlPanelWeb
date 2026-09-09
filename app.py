"""Точка входа приложения Flask"""
from flask import Flask
from database import db
from config import SECRET_KEY
from routes import register_blueprints

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Автоматический вызов при старте WSGI-контейнера на Vercel
try:
    db.init()
except Exception as e:
    print(f"Ошибка при db.init(): {e}")

# Регистрация всех маршрутов
register_blueprints(app)

if __name__ == "__main__":
    print("Запуск сервера на http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)