"""
Тест всех статусов чек-инов для пользователя aaaa@gmail.com
- Два дня назад с чек-ином → ✅ Пришёл
- Вчера без чек-ина → ❌ Не явился
- Сегодня → ⏳ Ожидается (или кнопка)
- Завтра → ⏳ Ожидается

Запуск: python script.py
"""
import sqlite3
from datetime import datetime, timedelta


TARGET_USERNAME = "aaaa@gmail.com"


def create_all_statuses():
    """Создаёт записи для проверки всех статусов"""
    conn = sqlite3.connect('duty.db')
    cursor = conn.cursor()

    # Ищем конкретного пользователя по username (email)
    cursor.execute(
        "SELECT user_id, fio, approval_status FROM users WHERE username = ?",
        (TARGET_USERNAME,)
    )
    user = cursor.fetchone()

    if not user:
        print(f'❌ Пользователь {TARGET_USERNAME} не найден в БД')
        print()
        print('Список всех пользователей:')
        cursor.execute("SELECT username, fio FROM users")
        for u in cursor.fetchall():
            print(f'  • {u[0]} — {u[1]}')
        conn.close()
        return

    user_id, fio, approval_status = user

    if approval_status != 'approved':
        print(f'⚠️ Пользователь {TARGET_USERNAME} не подтверждён (статус: {approval_status})')
        print('Сначала подтвердите пользователя в админке.')
        conn.close()
        return

    # Даты
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    two_days_ago = today - timedelta(days=2)
    tomorrow = today + timedelta(days=1)

    yesterday_str = yesterday.strftime('%d.%m.%Y')
    two_days_ago_str = two_days_ago.strftime('%d.%m.%Y')
    today_str = today.strftime('%d.%m.%Y')
    tomorrow_str = tomorrow.strftime('%d.%m.%Y')

    # Очищаем старые тестовые записи
    test_dates = [yesterday_str, two_days_ago_str, today_str, tomorrow_str]

    for date_str in test_dates:
        # Удаляем чек-ины
        cursor.execute(
            'DELETE FROM checkins WHERE date_str = ? AND user_id = ?',
            (date_str, user_id)
        )

        # Удаляем записи из расписания для этой даты (если там только наш пользователь)
        cursor.execute('DELETE FROM schedule WHERE date_str = ?', (date_str,))

    # 1. Два дня назад — был чек-ин (✅ Пришёл)
    cursor.execute('''
        INSERT OR REPLACE INTO schedule (date_str, slot1, slot2, slot3, slot4)
        VALUES (?, ?, '', '', '')
    ''', (two_days_ago_str, fio))

    cursor.execute('''
        INSERT OR REPLACE INTO checkins (user_id, fio, date_str, slot, shift, checkin_time)
        VALUES (?, ?, ?, 0, 1, '10:05')
    ''', (user_id, fio, two_days_ago_str))

    # 2. Вчера — НЕ было чек-ина (❌ Не явился)
    cursor.execute('''
        INSERT OR REPLACE INTO schedule (date_str, slot1, slot2, slot3, slot4)
        VALUES (?, ?, '', '', '')
    ''', (yesterday_str, fio))

    # 3. Сегодня — запись без чек-ина (⏳ Ожидается / кнопка)
    cursor.execute('''
        INSERT OR REPLACE INTO schedule (date_str, slot1, slot2, slot3, slot4)
        VALUES (?, ?, '', '', '')
    ''', (today_str, fio))

    # 4. Завтра — запись без чек-ина (⏳ Ожидается)
    cursor.execute('''
        INSERT OR REPLACE INTO schedule (date_str, slot1, slot2, slot3, slot4)
        VALUES (?, ?, '', '', '')
    ''', (tomorrow_str, fio))

    conn.commit()
    conn.close()

    print('=' * 60)
    print('✅ Тестовые записи созданы!')
    print('=' * 60)
    print()
    print(f'👤 Пользователь: {fio}')
    print(f'📧 Логин: {TARGET_USERNAME}')
    print()
    print('Что должно быть в /stats:')
    print(f'  📅 {two_days_ago_str} → ✅ Пришёл в 10:05')
    print(f'  📅 {yesterday_str}    → ❌ Не явился')
    print(f'  📅 {today_str}        → ⏳ Ожидается (или кнопка "Я пришёл")')
    print(f'  📅 {tomorrow_str}     → ⏳ Ожидается')
    print()
    print('📊 Ожидаемая статистика:')
    print('   ✅ Пришёл: 1')
    print('   ❌ Не явился: 1')
    print('   📊 Явка: 50%')
    print()
    print(f'🔗 Зайди как {TARGET_USERNAME} в:')
    print(f'   http://localhost:5000/stats')
    print(f'   http://localhost:5000/day/{today_str}')


if __name__ == '__main__':
    create_all_statuses()