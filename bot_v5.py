import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import pytz

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота (ВСТАВЬ СВОЙ ТОКЕН СЮДА!)
TOKEN = "8553012206:AAFl-KSaPj99_1oL0ZsDAaEdpEPWEISx4rY"

# Временная зона (Москва)
TIMEZONE = pytz.timezone('Europe/Moscow')

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    
    # Таблица напоминаний с категориями
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            text TEXT NOT NULL,
            remind_time TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sent INTEGER DEFAULT 0
        )
    ''')
    
    # Таблица дней рождения
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS birthdays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    
    # Таблица праздников
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я твой помощник-напоминалка.\n\n"
        "📋 ДОБАВИТЬ:\n"
        "/w ГГГГ-ММ-ДД ЧЧ:ММ текст - работа\n"
        "/p ГГГГ-ММ-ДД ЧЧ:ММ текст - личное\n"
        "/b Имя ДД.ММ - день рождения\n"
        "/h Название ДД.ММ - праздник\n\n"
        "📦 МАССОВЫЙ ВВОД:\n"
        "/bb - дни рождения списком\n"
        "/hh - праздники списком\n\n"
        "📊 ПОСМОТРЕТЬ:\n"
        "/wl - рабочие задачи\n"
        "/pl - личные дела\n"
        "/bl - дни рождения\n"
        "/hl - праздники\n"
        "/all - всё вместе\n\n"
        "🗑 УДАЛИТЬ:\n"
        "/d ID - удалить по номеру\n\n"
        "❓ /help - эта справка"
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# Универсальная функция добавления напоминания
async def add_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    user_id = update.effective_user.id
    
    if len(context.args) < 3:
        category_name = "рабочее" if category == "work" else "личное"
        cmd = "w" if category == "work" else "p"
        await update.message.reply_text(
            f"❌ Неправильный формат!\n\n"
            f"Используй: /{cmd} ГГГГ-ММ-ДД ЧЧ:ММ текст\n"
            f"Пример: /{cmd} 2026-09-10 09:00 Позвонить клиенту"
        )
        return
    
    date_str = context.args[0]
    time_str = context.args[1]
    text = ' '.join(context.args[2:])
    
    try:
        # Парсим дату и время
        remind_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        remind_time = TIMEZONE.localize(remind_time)
        
        # Проверяем, что время в будущем
        if remind_time <= datetime.now(TIMEZONE):
            await update.message.reply_text("❌ Время должно быть в будущем!")
            return
        
        # Сохраняем в базу
        conn = sqlite3.connect('reminders.db')
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO reminders (user_id, category, text, remind_time, created_at) VALUES (?, ?, ?, ?, ?)',
            (user_id, category, text, remind_time.isoformat(), datetime.now(TIMEZONE).isoformat())
        )
        conn.commit()
        reminder_id = cursor.lastrowid
        conn.close()
        
        # Создаём job для отправки напоминания
        delay = (remind_time - datetime.now(TIMEZONE)).total_seconds()
        context.job_queue.run_once(
            send_reminder,
            delay,
            data={'user_id': user_id, 'text': text, 'reminder_id': reminder_id, 'category': category}
        )
        
        emoji = "📋" if category == "work" else "💝"
        category_name = "Рабочее" if category == "work" else "Личное"
        
        await update.message.reply_text(
            f"✅ {category_name} добавлено!\n\n"
            f"{emoji} {text}\n"
            f"📅 {remind_time.strftime('%d.%m.%Y %H:%M')}\n"
            f"🆔 ID: {reminder_id}"
        )
        
    except ValueError:
        cmd = "w" if category == "work" else "p"
        await update.message.reply_text(
            "❌ Неправильный формат даты или времени!\n\n"
            f"Используй: /{cmd} ГГГГ-ММ-ДД ЧЧ:ММ текст\n"
            f"Пример: /{cmd} 2026-09-10 09:00 Позвонить клиенту"
        )

# Команда /w - рабочая задача
async def work_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_reminder(update, context, "work")

# Команда /p - личное дело
async def personal_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_reminder(update, context, "personal")

# Отправка напоминания
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    user_id = job_data['user_id']
    text = job_data['text']
    reminder_id = job_data['reminder_id']
    category = job_data.get('category', 'personal')
    
    emoji = "📋" if category == "work" else "💝"
    category_name = "РАБОТА" if category == "work" else "ЛИЧНОЕ"
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"⏰ {category_name}!\n\n{emoji} {text}"
        )
        
        # Помечаем как отправленное
        conn = sqlite3.connect('reminders.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE reminders SET sent = 1 WHERE id = ?', (reminder_id,))
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания {reminder_id}: {e}")

# Команда /b - день рождения
async def birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Неправильный формат!\n\n"
            "Используй: /b Имя ДД.ММ\n"
            "Пример: /b Мама 12.05"
        )
        return
    
    name = ' '.join(context.args[:-1])
    date_str = context.args[-1]
    
    try:
        # Парсим дату
        birthday_date = datetime.strptime(date_str, "%d.%m")
        
        # Сохраняем в базу
        conn = sqlite3.connect('reminders.db')
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO birthdays (user_id, name, date, created_at) VALUES (?, ?, ?, ?)',
            (user_id, name, birthday_date.strftime("%d.%m"), datetime.now(TIMEZONE).isoformat())
        )
        conn.commit()
        birthday_id = cursor.lastrowid
        conn.close()
        
        await update.message.reply_text(
            f"🎂 День рождения добавлен!\n\n"
            f"👤 {name}\n"
            f"📅 {birthday_date.strftime('%d.%m')}\n"
            f"🆔 ID: {birthday_id}\n\n"
            "Напомню за день до даты!"
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ Неправильный формат даты!\n\n"
            "Используй: /b Имя ДД.ММ\n"
            "Пример: /b Мама 12.05"
        )

# Команда /h - праздник
async def holiday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Неправильный формат!\n\n"
            "Используй: /h Название ДД.ММ\n"
            "Пример: /h Новый год 01.01"
        )
        return
    
    name = ' '.join(context.args[:-1])
    date_str = context.args[-1]
    
    try:
        # Парсим дату
        holiday_date = datetime.strptime(date_str, "%d.%m")
        
        # Сохраняем в базу
        conn = sqlite3.connect('reminders.db')
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO holidays (user_id, name, date, created_at) VALUES (?, ?, ?, ?)',
            (user_id, name, holiday_date.strftime("%d.%m"), datetime.now(TIMEZONE).isoformat())
        )
        conn.commit()
        holiday_id = cursor.lastrowid
        conn.close()
        
        await update.message.reply_text(
            f"🎉 Праздник добавлен!\n\n"
            f"🎊 {name}\n"
            f"📅 {holiday_date.strftime('%d.%m')}\n"
            f"🆔 ID: {holiday_id}\n\n"
            "Напомню за день до праздника!"
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ Неправильный формат даты!\n\n"
            "Используй: /h Название ДД.ММ\n"
            "Пример: /h Новый год 01.01"
        )

# Команда /wl - рабочие задачи
async def work_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, text, remind_time FROM reminders WHERE user_id = ? AND category = ? AND sent = 0 ORDER BY remind_time',
        (user_id, 'work')
    )
    reminders = cursor.fetchall()
    conn.close()
    
    if not reminders:
        await update.message.reply_text("📋 Нет рабочих задач.")
        return
    
    message = "📋 РАБОЧИЕ ЗАДАЧИ:\n\n"
    for reminder in reminders:
        remind_id, text, remind_time = reminder
        dt = datetime.fromisoformat(remind_time)
        message += f"🆔 {remind_id} | {dt.strftime('%d.%m %H:%M')}\n{text}\n\n"
    
    await update.message.reply_text(message)

# Команда /pl - личные дела
async def personal_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, text, remind_time FROM reminders WHERE user_id = ? AND category = ? AND sent = 0 ORDER BY remind_time',
        (user_id, 'personal')
    )
    reminders = cursor.fetchall()
    conn.close()
    
    if not reminders:
        await update.message.reply_text("💝 Нет личных дел.")
        return
    
    message = "💝 ЛИЧНЫЕ ДЕЛА:\n\n"
    for reminder in reminders:
        remind_id, text, remind_time = reminder
        dt = datetime.fromisoformat(remind_time)
        message += f"🆔 {remind_id} | {dt.strftime('%d.%m %H:%M')}\n{text}\n\n"
    
    await update.message.reply_text(message)

# Команда /all - все напоминания
async def list_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, category, text, remind_time FROM reminders WHERE user_id = ? AND sent = 0 ORDER BY remind_time',
        (user_id,)
    )
    reminders = cursor.fetchall()
    conn.close()
    
    if not reminders:
        await update.message.reply_text("📋 Нет напоминаний.")
        return
    
    message = "📊 ВСЁ:\n\n"
    for reminder in reminders:
        remind_id, category, text, remind_time = reminder
        emoji = "📋" if category == "work" else "💝"
        dt = datetime.fromisoformat(remind_time)
        message += f"{emoji} 🆔 {remind_id} | {dt.strftime('%d.%m %H:%M')}\n{text}\n\n"
    
    await update.message.reply_text(message)

# Команда /bl - дни рождения
async def list_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, name, date FROM birthdays WHERE user_id = ? ORDER BY date',
        (user_id,)
    )
    birthdays = cursor.fetchall()
    conn.close()
    
    if not birthdays:
        await update.message.reply_text("🎂 Нет дней рождения.")
        return
    
    message = "🎂 ДНИ РОЖДЕНИЯ:\n\n"
    for birthday in birthdays:
        birthday_id, name, date = birthday
        message += f"🆔 {birthday_id} | {name} - {date}\n"
    
    await update.message.reply_text(message)

# Команда /hl - праздники
async def list_holidays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, name, date FROM holidays WHERE user_id = ? ORDER BY date',
        (user_id,)
    )
    holidays = cursor.fetchall()
    conn.close()
    
    if not holidays:
        await update.message.reply_text("🎉 Нет праздников.")
        return
    
    message = "🎉 ПРАЗДНИКИ:\n\n"
    for holiday_item in holidays:
        holiday_id, name, date = holiday_item
        message += f"🆔 {holiday_id} | {name} - {date}\n"
    
    await update.message.reply_text(message)

# Команда /d - удалить
async def delete_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if len(context.args) != 1:
        await update.message.reply_text("❌ Используй: /d ID\nПример: /d 5")
        return
    
    try:
        reminder_id = int(context.args[0])
        
        conn = sqlite3.connect('reminders.db')
        cursor = conn.cursor()
        cursor.execute(
            'DELETE FROM reminders WHERE id = ? AND user_id = ?',
            (reminder_id, user_id)
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted:
            await update.message.reply_text(f"✅ Удалено {reminder_id}")
        else:
            await update.message.reply_text(f"❌ Не найдено {reminder_id}")
    
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом!")

# Команда /bb - массовое добавление дней рождения
async def bulk_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if len(context.args) == 0:
        await update.message.reply_text(
            "📦 Массовое добавление дней рождения\n\n"
            "Отправь мне список в формате:\n"
            "/bb\n"
            "Мама 12.05\n"
            "Папа 15.08\n"
            "Иван 03.11\n\n"
            "Или через пробел:\n"
            "/bb Мама 12.05 Папа 15.08 Иван 03.11"
        )
        return
    
    # Объединяем все аргументы в одну строку
    full_text = ' '.join(context.args)
    
    # Разбиваем на пары (имя дата)
    parts = full_text.split()
    
    added = 0
    errors = []
    
    i = 0
    while i < len(parts):
        if i + 1 < len(parts):
            name = parts[i]
            date_str = parts[i + 1]
            
            try:
                # Парсим дату
                birthday_date = datetime.strptime(date_str, "%d.%m")
                
                # Сохраняем в базу
                conn = sqlite3.connect('reminders.db')
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO birthdays (user_id, name, date, created_at) VALUES (?, ?, ?, ?)',
                    (user_id, name, birthday_date.strftime("%d.%m"), datetime.now(TIMEZONE).isoformat())
                )
                conn.commit()
                conn.close()
                
                added += 1
            except ValueError:
                errors.append(f"{name} {date_str}")
            
            i += 2
        else:
            i += 1
    
    message = f"✅ Добавлено дней рождения: {added}\n"
    if errors:
        message += f"\n❌ Ошибки в формате:\n" + "\n".join(errors)
    
    await update.message.reply_text(message)

# Команда /hh - массовое добавление праздников
async def bulk_holidays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if len(context.args) == 0:
        await update.message.reply_text(
            "📦 Массовое добавление праздников\n\n"
            "Отправь мне список в формате:\n"
            "/hh\n"
            "Новый_год 01.01\n"
            "8_марта 08.03\n"
            "День_Победы 09.05\n\n"
            "Внимание! Название праздника с пробелами пиши через _ (подчёркивание)\n"
            "Или через пробел:\n"
            "/hh Новый_год 01.01 8_марта 08.03"
        )
        return
    
    # Объединяем все аргументы в одну строку
    full_text = ' '.join(context.args)
    
    # Разбиваем на пары (название дата)
    parts = full_text.split()
    
    added = 0
    errors = []
    
    i = 0
    while i < len(parts):
        if i + 1 < len(parts):
            name = parts[i].replace('_', ' ')
            date_str = parts[i + 1]
            
            try:
                # Парсим дату
                holiday_date = datetime.strptime(date_str, "%d.%m")
                
                # Сохраняем в базу
                conn = sqlite3.connect('reminders.db')
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO holidays (user_id, name, date, created_at) VALUES (?, ?, ?, ?)',
                    (user_id, name, holiday_date.strftime("%d.%m"), datetime.now(TIMEZONE).isoformat())
                )
                conn.commit()
                conn.close()
                
                added += 1
            except ValueError:
                errors.append(f"{name} {date_str}")
            
            i += 2
        else:
            i += 1
    
    message = f"✅ Добавлено праздников: {added}\n"
    if errors:
        message += f"\n❌ Ошибки в формате:\n" + "\n".join(errors)
    
    await update.message.reply_text(message)

# Проверка напоминаний при запуске
async def check_pending_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет напоминания в базе и планирует их отправку"""
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, user_id, category, text, remind_time FROM reminders WHERE sent = 0')
    reminders = cursor.fetchall()
    conn.close()
    
    now = datetime.now(TIMEZONE)
    
    for reminder in reminders:
        reminder_id, user_id, category, text, remind_time = reminder
        remind_dt = datetime.fromisoformat(remind_time)
        
        delay = (remind_dt - now).total_seconds()
        
        if delay > 0:
            # Планируем отправку
            context.application.job_queue.run_once(
                send_reminder,
                delay,
                data={'user_id': user_id, 'text': text, 'reminder_id': reminder_id, 'category': category}
            )
        else:
            # Время уже прошло, отправляем сразу
            emoji = "📋" if category == "work" else "💝"
            category_name = "РАБОТА" if category == "work" else "ЛИЧНОЕ"
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⏰ {category_name}!\n\n{emoji} {text}"
                )
                conn = sqlite3.connect('reminders.db')
                cursor = conn.cursor()
                cursor.execute('UPDATE reminders SET sent = 1 WHERE id = ?', (reminder_id,))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Ошибка отправки напоминания {reminder_id}: {e}")

# Проверка дней рождения
async def check_birthdays_daily(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет дни рождения на завтра"""
    tomorrow = (datetime.now(TIMEZONE) + timedelta(days=1)).strftime("%d.%m")
    
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, name FROM birthdays WHERE date = ?', (tomorrow,))
    birthdays = cursor.fetchall()
    conn.close()
    
    for user_id, name in birthdays:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎂 Завтра день рождения у {name}!\n\nНе забудь поздравить! 🎉"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания о дне рождения: {e}")

# Проверка праздников
async def check_holidays_daily(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет праздники на завтра"""
    tomorrow = (datetime.now(TIMEZONE) + timedelta(days=1)).strftime("%d.%m")
    
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, name FROM holidays WHERE date = ?', (tomorrow,))
    holidays = cursor.fetchall()
    conn.close()
    
    for user_id, name in holidays:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 Завтра праздник: {name}!\n\nНе забудь подготовиться! 🎊"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания о празднике: {e}")

# Главная функция
def main():
    # Инициализируем базу данных
    init_db()
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("w", work_reminder))
    application.add_handler(CommandHandler("p", personal_reminder))
    application.add_handler(CommandHandler("b", birthday))
    application.add_handler(CommandHandler("h", holiday))
    application.add_handler(CommandHandler("bb", bulk_birthdays))
    application.add_handler(CommandHandler("hh", bulk_holidays))
    application.add_handler(CommandHandler("wl", work_list))
    application.add_handler(CommandHandler("pl", personal_list))
    application.add_handler(CommandHandler("all", list_all))
    application.add_handler(CommandHandler("bl", list_birthdays))
    application.add_handler(CommandHandler("hl", list_holidays))
    application.add_handler(CommandHandler("d", delete_reminder))
    
    # Проверяем существующие напоминания при запуске
    application.job_queue.run_once(check_pending_reminders, 5)
    
    # Проверяем дни рождения каждый день в 9:00
    application.job_queue.run_daily(
        check_birthdays_daily,
        time=datetime.strptime("09:00", "%H:%M").time(),
        days=(0, 1, 2, 3, 4, 5, 6)
    )
    
    # Проверяем праздники каждый день в 9:00
    application.job_queue.run_daily(
        check_holidays_daily,
        time=datetime.strptime("09:00", "%H:%M").time(),
        days=(0, 1, 2, 3, 4, 5, 6)
    )
    
    # Запускаем бота
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
