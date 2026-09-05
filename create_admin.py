from database import db

db.init()

username = "admin"
password = "654321"
fio = "admin"

success, msg = db.register_user(username, password, fio, "admin")

if success:
    db.approve_user(username)
    print("Админ создан и подтверждён.")
else:
    print(msg)