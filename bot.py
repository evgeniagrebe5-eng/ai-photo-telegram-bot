import os
import shutil
import io
import json
import base64
import asyncio
import logging
import sqlite3  # Добавили для постоянного хранения данных
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ADMIN_ID = os.environ.get("ADMIN_ID")
CHANNEL_USERNAME = "@galereyapromt"
BOT_USERNAME = "aiphoto_gallery_bot"

# Укажите путь к вашему подключенному диску. 
# Например, если диск примонтирован в папку /data, путь будет "/data/bot_database.db"
# Если диск примонтирован в текущую папку, оставьте "bot_database.db"
DB_PATH = os.environ.get("DB_PATH", "bot_database.db")
PHOTOS_DIR = os.environ.get("PHOTOS_DIR", "stored_photos") # Папка на диске для физических фото

# Создаем папку для фото, если её нет
os.makedirs(PHOTOS_DIR, exist_ok=True)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID is not set")
try:
    ADMIN_ID = int(ADMIN_ID)
except ValueError:
    raise RuntimeError("ADMIN_ID must be a number")

client = OpenAI(api_key=OPENAI_API_KEY)

DEFAULT_SESSIONS = {
    "autumn": {"title": "🍂 Осенняя", "prompt": """Создай профессиональную фотореалистичную осеннюю fashion-фотосессию..."""},
    "luxury": {"title": "💎 Luxury", "prompt": """Создай роскошную профессиональную fashion-фотографию..."""},
    "fashion": {"title": "👠 Fashion", "prompt": """Создай современную профессиональную fashion-фотографию..."""},
    "love": {"title": "❤️ Love Story", "prompt": """Создай романтическую профессиональную фотографию..."""},
    "romantic": {"title": "🌸 Romantic", "prompt": """Создай неную романтическую fashion-фотографию..."""},
    "black": {"title": "🖤 Black Editorial", "prompt": """Создай профессиональную драматичную fashion editorial фотографию..."""},
    "child": {"title": "👶 Детская фотосессия", "prompt": """Создай профессиональную детскую фотосессию..."""},
    "man": {"title": "🤵 Мужская фотосессия", "prompt": """Создай профессиональную мужскую fashion-фотосессию..."""},
}

# ==========================================
# БЛОК РАБОТЫ С БАЗОЙ ДАННЫХ (ФИКС ОЧИСТКИ)
# ==========================================

def init_db():
    """Инициализирует базу данных на постоянном диске."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица для хранения типов фотосессий (чтобы админ мог ими управлять)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            key TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            prompt TEXT NOT NULL
        )
    ''')
    
    # Таблица для хранения сгенерированных фотографий, их промтов и связей с сессиями
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS generated_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_key TEXT,
            photo_path TEXT,      -- Путь к файлу на постоянном диске
            tg_file_id TEXT,      -- ID файла в Telegram (для быстрой отправки)
            channel_msg_id TEXT,  -- ID сообщения в канале галереи
            prompt TEXT,          -- Промт, с которым была генерация
            user_id INTEGER,      -- Кто сгенерировал
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_key) REFERENCES sessions(key)
        )
    ''')
    
    # Заполняем дефолтными сессиями, если таблица пуста
    cursor.execute("SELECT COUNT(*) FROM sessions")
    if cursor.fetchone()[0] == 0:
        for key, data in DEFAULT_SESSIONS.items():
            cursor.execute(
                "INSERT INTO sessions (key, title, prompt) VALUES (?, ?, ?)",
                (key, data["title"], data["prompt"])
            )
        conn.commit()
        logger.info("Дефолтные фотосессии успешно записаны в БД.")
        
    conn.close()

# Запускаем инициализацию базы данных при старте скрипта
init_db()

def get_all_sessions():
    """Получить все доступные сессии из БД (для меню)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT key, title, prompt FROM sessions")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: {"title": row[1], "prompt": row[2]} for row in rows}

def save_generated_photo(session_key, photo_path, tg_file_id, channel_msg_id, prompt, user_id):
    """Сохраняет данные о фотографии навсегда в БД"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO generated_photos (session_key, photo_path, tg_file_id, channel_msg_id, prompt, user_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (session_key, photo_path, tg_file_id, channel_msg_id, prompt, user_id))
    conn.commit()
    conn.close()
    logger.info(f"Фотосессия сохранена в БД для сессии {session_key}")
# =========================
# PERMANENT STORAGE - RENDER (FIXED)
# =========================

DATA_DIR = "/var/data"
os.makedirs(DATA_DIR, exist_ok=True)
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
os.makedirs(PHOTOS_DIR, exist_ok=True)

SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
PROMPTS_FILE = os.path.join(DATA_DIR, "prompts.json")  # Здесь будем хранить историю фото + промтов
FREE_USERS_FILE = os.path.join(DATA_DIR, "free_users.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

# Миграция файлов из старой структуры приложения на постоянный диск Render
for filename in ("sessions.json", "prompts.json", "free_users.json", "users.json"):
    old_path = os.path.abspath(os.path.join("data", filename))
    if filename == "sessions.json":
        candidates = [old_path, os.path.abspath(filename)]
        destination = SESSIONS_FILE
    else:
        candidates = [os.path.abspath(os.path.join("data", filename)), os.path.abspath(filename)]
        destination = os.path.join(DATA_DIR, filename)

    if not os.path.exists(destination):
        for candidate in candidates:
            if os.path.isfile(candidate) and os.path.abspath(candidate) != os.path.abspath(destination):
                shutil.copy2(candidate, destination)
                logger.info("Migrated %s to persistent storage", candidate)
                break

# ---------------------------------------------
# 1. УПРАВЛЕНИЕ СЕССИЯМИ (ШАБЛОНАМИ ПРОМТОВ)
# ---------------------------------------------
def save_sessions(data=None):
    """Атомарно сохраняет шаблоны сессий на диск Render."""
    if data is None:
        data = SESSIONS
    os.makedirs(DATA_DIR, exist_ok=True)
    temp_file = SESSIONS_FILE + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, SESSIONS_FILE)
        logger.info("SESSIONS SAVED: %s (%s sessions)", SESSIONS_FILE, len(data))
    except Exception:
        logger.exception("ERROR SAVING SESSIONS")
        raise

def load_sessions():
    """Загружает шаблоны сессий с диска Render."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(SESSIONS_FILE):
        # DEFAULT_SESSIONS берется из вашей первой части кода
        data = json.loads(json.dumps(DEFAULT_SESSIONS, ensure_ascii=False))
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Created default sessions file: %s", SESSIONS_FILE)
        return data

    with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Некорректный формат sessions.json: ожидался JSON-объект")
    return data

# Глобальная переменная сессий, загруженная из диска Render
SESSIONS = load_sessions()

# ---------------------------------------------
# 2. НОВЫЙ БЛОК: СОХРАНЕНИЕ ФОТОСЕССИЙ (ИСТОРИИ ГЕНЕРАЦИЙ)
# ---------------------------------------------
def load_prompts_history():
    """Загружает всю историю генераций (фотосессий) пользователей."""
    if not os.path.exists(PROMPTS_FILE):
        return {}  # Возвращает пустой словарь, если истории еще нет
    try:
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Ошибка при загрузке истории генераций (prompts.json)")
        return {}

def save_photo_to_history(photo_id, session_key, photo_path, tg_file_id, channel_msg_id, prompt, user_id):
    """
    Записывает сгенерированное фото навсегда в prompts.json на диске Render.
    Вызывается сразу после успешного рендера и публикации в канал!
    """
    history = load_prompts_history()
    
    # Добавляем или обновляем запись
    history[str(photo_id)] = {
        "session_key": session_key,
        "photo_path": photo_path,          # Полный путь к файлу в /var/data/photos/
        "tg_file_id": tg_file_id,          # ID фото в Telegram для быстрого отображения
        "channel_msg_id": channel_msg_id,  # Связь с постом в канале галереи
        "prompt": prompt,                  # Сам промт, с которым шла генерация
        "user_id": user_id,                # Кто создал
        "timestamp": os.path.getmtime(photo_path) if os.path.exists(photo_path) else None
    }
    
    temp_file = PROMPTS_FILE + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, PROMPTS_FILE)
        logger.info(f"Фото {photo_id} успешно привязано к промту и сохранено на диске Render.")
    except Exception:
        logger.exception("Ошибка сохранения истории генерации в prompts.json")

# ---------------------------------------------
# 3. УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ
# ---------------------------------------------
def load_free_users():
    if not os.path.exists(FREE_USERS_FILE):
        return set()
    try:
        with open(FREE_USERS_FILE, "r", encoding="utf-8") as f:
            return {str(x) for x in json.load(f)}
    except Exception:
        logger.exception("Error loading free_users.json")
        return set()

def save_free_users(users):
    with open(FREE_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(users), f, ensure_ascii=False, indent=2)
FREE_USERS = load_free_users()
SESSIONS = load_sessions()

# Гарантируем существование директории на постоянном диске Render
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
os.makedirs(PHOTOS_DIR, exist_ok=True)

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("Error loading users.json")
        return {}

def save_users(users):
    temp_file = USERS_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_file, USERS_FILE)

USERS = load_users()
telegram_app = Application.builder().token(BOT_TOKEN).build()

def client_keyboard():
    buttons = [
        [InlineKeyboardButton(s["title"], callback_data=f"style:{k}")]
        for k, s in SESSIONS.items()
    ]
    buttons.append([
        InlineKeyboardButton("✨ СВОЙ ПРОМТ", callback_data="custom_prompt")
    ])
    return InlineKeyboardMarkup(buttons)

def payment_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 1 фото — 500 ₸", callback_data="buy:1")],
        [InlineKeyboardButton("📸 3 фото — 1 200 ₸", callback_data="buy:3")],
        [InlineKeyboardButton("📸 5 фото — 1 800 ₸", callback_data="buy:5")],
        [InlineKeyboardButton("📸 10 фото — 3 000 ₸", callback_data="buy:10")],
    ])

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить фотосессию", callback_data="admin:add")],
        [InlineKeyboardButton("✏️ Изменить промт", callback_data="admin:edit")],
        [InlineKeyboardButton("🗑 Удалить фотосессию", callback_data="admin:delete")],
        [InlineKeyboardButton("📢 Пост в канал", callback_data="admin:channel")],
        [InlineKeyboardButton("📋 Мои фотосессии", callback_data="admin:list")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="admin:home")],
    ])

def is_admin(update):
    return bool(update.effective_user and str(update.effective_user.id) == str(ADMIN_ID))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if context.args and context.args[0] in SESSIONS:
        style = context.args[0]
        context.user_data["selected_style"] = style
        await update.message.reply_text(
            f"✨ Выбрана фотосессия:\n\n{SESSIONS[style]['title']}\n\n"
            "📸 Теперь просто отправь свою фотографию.\n"
            "Промт писать не нужно — я всё сделаю сама ❤️"
        )
        return
    await update.message.reply_text(
        "✨ Добро пожаловать в AI Photo Gallery!\n\n"
        "Выбери фотосессию 👇\n\n"
        "После выбора просто отправь фотографию 📸\n"
        "Промт писать не нужно — я всё сделаю сама ❤️",
        reply_markup=client_keyboard(),
    )

async def admin_command(update, context):
    if not is_admin(update):
        await update.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return
    context.user_data.clear()
    await update.message.reply_text("👑 Панель администратора\n\nВыбери действие:", reply_markup=admin_keyboard())

async def callback_handler(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("style:"):
        key = data.split(":", 1)[1]
        if key not in SESSIONS:
            await query.message.reply_text("❌ Эта фотосессия больше недоступна.")
            return

        context.user_data["selected_style"] = key
        gallery_items = SESSIONS[key].get("gallery_items", [])

        if gallery_items:
            await query.message.reply_text(
                f"{SESSIONS[key]['title']}\n\n✨ Выбери понравившийся образ 👇"
            )
            for index, item in enumerate(gallery_items):
                caption = item.get("caption", "").strip()
                text = SESSIONS[key]["title"]
                if caption:
                    text += f"\n\n{caption}"

                await query.message.reply_photo(
                    photo=item["reference_image_file_id"],
                    caption=text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📸 СДЕЛАТЬ ТАКОЕ ФОТО", callback_data=f"gallery:{key}:{index}")]
                    ])
                )
            return

        await query.message.reply_text(
            f"{SESSIONS[key]['title']}\n\n"
            "Отлично ❤️\nТеперь просто отправь свою фотографию 📸\n\nПромт писать не нужно."
        )
        return 

    if data.startswith("gallery:"):
        parts = data.split(":", 2)
        if len(parts) != 3:
            return
        key = parts[1]
        try:
            index = int(parts[2])
        except ValueError:
            return

        if key not in SESSIONS:
            await query.message.reply_text("❌ Эта фотосессия больше недоступна.")
            return

        gallery_items = SESSIONS[key].get("gallery_items", [])
        if index < 0 or index >= len(gallery_items):
            await query.message.reply_text("❌ Этот образ больше недоступна.")
            return

        context.user_data["selected_style"] = key
        context.user_data["selected_gallery_index"] = index

        await query.message.reply_text(
            f"📸 Отличный выбор!\n\n{SESSIONS[key]['title']}\n\nТеперь отправь свою фотографию 📸"
        )
        return
 
    if data.startswith("buy:"):
        package = data.split(":", 1)[1]
        packages = {
            "1": ("1 фото", 500),
            "3": ("3 фото", 1200),
            "5": ("5 фото", 1800),
            "10": ("10 фото", 3000),
        }
        if package not in packages:
            return
        title, price = packages[package]

        await query.message.reply_text(
            f"💳 Пакет: {title}\nСтоимость: {price} ₸\n\n"
            "Нажми кнопку ниже, чтобы получить реквизиты для оплаты 👇",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 ПОКАЗАТЬ РЕКВИЗИТЫ", callback_data=f"details:{package}")]
            ])
        )
        return

    if data.startswith("details:"):
        package = data.split(":", 1)[1]
        packages = {
            "1": ("1 фото", 500),
            "3": ("3 фото", 1200),
            "5": ("5 фото", 1800),
            "10": ("10 фото", 3000),
        }
        if package not in packages:
            return
        title, price = packages[package]

        await query.message.reply_text(
            f"💳 Оплата пакета: {title}\nСумма: {price} ₸\n\n"
            "Переведи указанную сумму на Kaspi.\nНомер для перевода: +7 777 878 00 78\n\n"
            "После оплаты нажми кнопку ниже 👇",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Я оплатил(а)", callback_data=f"paid:{package}")]
            ])
        )
        return      

    if data.startswith("paid:"):
        package = data.split(":", 1)[1]
        # Завершаем оборванную кнопку подтверждения для админа, передаем ID пользователя и пакет
        user_id = query.from_user.id
        user_name = query.from_user.full_name
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "💳 НОВАЯ ОПЛАТА\n\n"
                f"Пакет: {package} фото\n"
                f"Пользователь: {user_name}\n"
                f"Telegram ID: {user_id}\n\n"
                "Проверь оплату в Kaspi и нажми кнопку ниже."
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ ПОДТВЕРДИТЬ ОПЛАТУ", callback_data=f"confirm_pay:{user_id}:{package}")]
            ])
        )
        await query.message.reply_text("⏳ Ваша заявка отправлена администратору. Ожидайте подтверждения.")
        return
    # ==========================================
    # 👑 ОБРАБОТКА НАЖАТИЙ АДМИН-КНОПОК (ФИКС)
    # ==========================================
    if data.startswith("admin:"):
        if not is_admin(update):
            await query.message.reply_text("⛔ Доступ ограничен.")
            return
            
        action = data.split(":", 1)[1]
        
        # 1. Нажатие на кнопку "📢 Пост в канал"
        if action == "channel":
            context.user_data.clear()
            # Показываем админу кнопки с выбором стиля для канала
            buttons = [
                [InlineKeyboardButton(s["title"], callback_data=f"admin_ch_style:{k}")]
                for k, s in SESSIONS.items()
            ]
            await query.message.reply_text(
                "📢 Выбери фотосессию, к которой будет относиться пост в канале 👇",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        # 2. Нажатие на кнопку "📸 Добавить фото в фотосессию"
        elif action == "add_photo":
            context.user_data.clear()
            buttons = [
                [InlineKeyboardButton(s["title"], callback_data=f"admin_add_photo_style:{k}")]
                for k, s in SESSIONS.items()
            ]
            await query.message.reply_text(
                "📸 Выбери фотосессию, в галерею которой хочешь вручную добавить фото референса 👇",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        # 3. Нажатие на кнопку "🏠 Главное меню"
        elif action == "home":
            context.user_data.clear()
            await query.message.reply_text("Выбери фотосессию 👇", reply_markup=client_keyboard())
            return

    # Подхватываем выбор стиля для Поста в канал
    if data.startswith("admin_ch_style:"):
        key = data.split(":", 1)[1]
        context.user_data["channel_style"] = key
        context.user_data["admin_state"] = "waiting_channel_prompt"
        await query.message.reply_text(
            f"Выбрана сессия: {SESSIONS[key]['title']}\n\n"
            "✍️ Введи и отправь промт (prompt) для генерации этого поста:"
        )
        return

    # Подхватываем выбор стиля для Ручного добавления фото в фотосессию
    if data.startswith("admin_add_photo_style:"):
        key = data.split(":", 1)[1]
        context.user_data["edit_key"] = key
        context.user_data["admin_state"] = "waiting_admin_gallery_photo"
        await query.message.reply_text(
            f"Выбрана сессия: {SESSIONS[key]['title']}\n\n"
            "📸 Теперь просто отправь боту фотографию. Она автоматически скачается на диск Render и добавится в этот стиль!"
        )
        return
        
    # Обработчик подтверждения оплаты админом
    if data.startswith("confirm_pay:"):
        if not is_admin(update):
            return
        parts = data.split(":")
        target_user_id = parts[1]
        count = int(parts[2])
        
        # Обновляем баланс в нашей базе USERS и пишем на диск Render
        global USERS
        USERS = load_users()
        if target_user_id not in USERS:
            USERS[target_user_id] = {"balance": 0, "name": ""}
        
        USERS[target_user_id]["balance"] = USERS[target_user_id].get("balance", 0) + count
        save_users(USERS)
        
        # Уведомляем пользователя
        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=f"✅ Оплата подтверждена! Вам начислено {count} фото. Можете начинать генерацию!"
            )
        except Exception:
            logger.exception("Не удалось отправить сообщение пользователю об оплате")
            
        await query.message.edit_text(f"🟢 Оплата для пользователя {target_user_id} на {count} фото успешно подтверждена.")
        return
    # ==========================================
    # 📢 АДМИН: ПОСТ В КАНАЛ (ЗАЩИТА ОТ УДАЛЕНИЯ)
    # ==========================================
    if is_admin(update) and context.user_data.get("admin_state") == "channel_photo":
        key = context.user_data.get("channel_style")
        caption = context.user_data.get("channel_caption", "")
        channel_prompt = context.user_data.get("channel_prompt", "").strip()

        if not key or key not in SESSIONS:
            context.user_data.clear()
            await update.message.reply_text(
                "❌ Не удалось найти фотосессию.",
                reply_markup=admin_keyboard()
            )
            return

        if not channel_prompt:
            await update.message.reply_text(
                "❌ Промт не найден.\n\nНачни создание поста заново."
            )
            return

        try:
            # Получаем фото, которое прислал администратор
            telegram_file = await update.message.photo[-1].get_file()
            photo_bytes = await telegram_file.download_as_bytearray()

            image_file = io.BytesIO(bytes(photo_bytes))
            image_file.name = "channel_reference.jpg"

            await update.message.reply_text(
                "✨ Создаю изображение по твоему промту...\nНемного подожди 📸"
            )

            # Генерируем изображение по промту администратора
            def generate_channel_image():
                return client.images.edit(
                    model="gpt-image-2",
                    image=image_file,
                    prompt=channel_prompt,
                    size="1024x1536"
                )

            result = await asyncio.to_thread(generate_channel_image)

            if not result.data or not getattr(result.data[0], "b64_json", None):
                raise RuntimeError("OpenAI returned no image")

            generated_bytes = base64.b64decode(result.data[0].b64_json)

            # Готовим байты для отправки в Telegram канал
            output = io.BytesIO(generated_bytes)
            output.name = "channel_photo.png"

            # Кнопка под постом в канале для клиентов
            button = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📸 СДЕЛАТЬ ФОТО",
                        url=f"https://t.me/{BOT_USERNAME}?start={key}"
                    )
                ]
            ])

            # Публикуем ГОТОВОЕ сгенерированное изображение в канал
            channel_message = await context.bot.send_photo(
                chat_id=CHANNEL_USERNAME,
                photo=output,
                caption=caption,
                reply_markup=button
            )

            generated_file_id = None
            if channel_message.photo:
                generated_file_id = channel_message.photo[-1].file_id

            # ЕСЛИ ФОТО УСПЕШНО ОПУБЛИКОВАНО В КАНАЛ, ЖЕСТКО СОХРАНЯЕМ НА ДИСК RENDER
            if generated_file_id:
                try:
                    # 1. Скачиваем физический файл с серверов Telegram в постоянную папку /var/data/photos/
                    tg_file = await context.bot.get_file(generated_file_id)
                    local_filename = f"{generated_file_id}.jpg"
                    local_photo_path = os.path.join(PHOTOS_DIR, local_filename)
                    await tg_file.download_to_drive(local_photo_path)
                    
                    # 2. Инициализируем массив галереи образов в сессии, если его нет
                    if "gallery_items" not in SESSIONS[key]:
                        SESSIONS[key]["gallery_items"] = []
                    
                    # Обновляем главный file_id сессии
                    SESSIONS[key]["reference_image_file_id"] = generated_file_id
                    
                    # 3. Сохраняем КЛЮЧЕВУЮ СВЯЗКУ: и file_id (для мгновенной отправки),
                    # и local_path (чтобы переотправить файл с диска, если Telegram обнулит ID)
                    SESSIONS[key]["gallery_items"].append({
                        "reference_image_file_id": generated_file_id, # Оставляем для совместимости с кодом отправки
                        "local_path": local_photo_path,               # Подстраховка на диске Render
                        "prompt": channel_prompt,
                        "caption": caption,
                        "channel_message_id": channel_message.message_id # Айди поста в канале
                    })
                    
                    # 4. Записываем изменения в файл sessions.json на постоянный диск Render!
                    save_sessions(SESSIONS)
                    logger.info("GALLERY SAVED: session=%s, items=%s", key, len(SESSIONS[key]["gallery_items"]))
                    
                except Exception as e:
                    logger.error(f"Ошибка при скачивании фото на постоянный диск Render: {e}")
            else:
                logger.error("GALLERY ERROR: channel photo file_id not found")

            # Очищаем состояние админа после успешного завершения
            context.user_data.clear()

            await update.message.reply_text(
                "✅ Готово!\n\nИзображение создано по твоему промту и опубликовано в канал 📢",
                reply_markup=admin_keyboard()
            )

        except Exception as e:
            logger.exception("Критическая ошибка в блоке отправки в канал")
            await update.message.reply_text(
                f"❌ Произошла ошибка при генерации или отправке: {e}",
                reply_markup=admin_keyboard()
            )
            context.user_data.clear()
        # ==========================================
        # 🛠️ АДМИН: РУЧНОЕ ДОБАВЛЕНИЕ ФОТО В СЕССИЮ
        # ==========================================
        if is_admin(update) and context.user_data.get("admin_state") == "add_photo_photo":
            edit_key = context.user_data.get("add_photo_key")

            if not edit_key or edit_key not in SESSIONS:
                context.user_data.clear()
                await update.message.reply_text(
                    "❌ Ошибка: фотосессия не найдена."
                )
                return

            # Получаем file_id присланного фото
            admin_file_id = update.message.photo[-1].file_id

            try:
                # 1. Скачиваем физический файл на постоянный диск Render
                tg_file = await context.bot.get_file(admin_file_id)
                local_filename = f"admin_{admin_file_id}.jpg"
                local_photo_path = os.path.join(PHOTOS_DIR, local_filename)
                await tg_file.download_to_drive(local_photo_path)

                # 2. Инициализируем галерею, если её ещё нет
                if "gallery_items" not in SESSIONS[edit_key]:
                    SESSIONS[edit_key]["gallery_items"] = []

                # 3. Сохраняем фото в фотосессию
                SESSIONS[edit_key]["gallery_items"].append({
                    "local_path": local_photo_path,
                    "reference_image_file_id": admin_file_id,
                    "prompt": SESSIONS[edit_key].get(
                        "prompt",
                        "Добавлено вручную через админку"
                    ),
                    "caption": ""
                })

                # 4. Сохраняем обновлённую сессию
                save_sessions(SESSIONS)

                logger.info(
                    "MANUAL PHOTO SAVED: session=%s, path=%s, items=%s",
                    edit_key,
                    local_photo_path,
                    len(SESSIONS[edit_key]["gallery_items"])
                )

                context.user_data.clear()

                await update.message.reply_text(
                    "✅ Фотография успешно добавлена в фотосессию и сохранена на диск!"
                )

            except Exception as e:
                logger.exception(
                    f"Ошибка при сохранении фото из админки: {e}"
                )
                await update.message.reply_text(
                    "❌ Не удалось сохранить файл на диск. Проверьте логи."
                )

            return        
    # =========================
    # 📸 КЛИЕНТСКАЯ ГЕНЕРАЦИЯ
    # =========================
    custom_prompt = context.user_data.get("custom_prompt") if context.user_data.get("custom_prompt_state") == "waiting_photo" else None
    style = context.user_data.get("selected_style")

    if custom_prompt:
        session = {"title": "✨ Свой промт", "prompt": custom_prompt}
        style = None
    elif not style or style not in SESSIONS:
        await update.message.reply_text(
            "❌ Сначала выбери фотосессию или нажми «СВОЙ ПРОМТ».",
            reply_markup=client_keyboard()
        )
        return
    else:
        session = SESSIONS[style]

    user_id_str = str(update.effective_user.id)
    user_record = USERS.get(user_id_str, {})
    paid_photos = int(user_record.get("paid_photos", 0) or 0)
    has_free = user_id_str in FREE_USERS or bool(context.user_data.get("free_used"))
    using_paid_credit = not is_admin(update) and paid_photos > 0
    using_free_credit = not is_admin(update) and not using_paid_credit and not has_free

    if not is_admin(update) and not using_paid_credit and not using_free_credit:
        await update.message.reply_text(
            "🎁 Бесплатная генерация уже использована.\n\nВыбери пакет фотографий 👇",
            reply_markup=payment_keyboard(),
        )
        return

    await update.message.reply_text(
        "📸 Фото получила!\n\n✨ Начинаю обработку...\nЭто может занять некоторое время."
    )

    try:
        telegram_file = await update.message.photo[-1].get_file()
        photo_bytes = await telegram_file.download_as_bytearray()

        image_file = io.BytesIO(bytes(photo_bytes))
        image_file.name = "photo.jpg"

        # Определение выбранного образа
        gallery_index = context.user_data.get("selected_gallery_index") if style else None
        gallery_items = session.get("gallery_items", [])
        selected_item = None

        if gallery_index is not None:
            if not (0 <= gallery_index < len(gallery_items)):
                context.user_data.pop("selected_gallery_index", None)
                await update.message.reply_text("❌ Этот образ больше недоступен. Выбери образ ещё раз.")
                return
            selected_item = gallery_items[gallery_index]
            reference_file_id = selected_item.get("reference_image_file_id")
            prompt_text = selected_item.get("prompt") or session.get("prompt", "")
        else:
            reference_file_id = session.get("reference_image_file_id") if style else None
            prompt_text = custom_prompt or session.get("prompt", "")

        reference_file = None
        if reference_file_id:
            reference_telegram_file = await context.bot.get_file(reference_file_id)
            reference_bytes = await reference_telegram_file.download_as_bytearray()
            reference_file = io.BytesIO(bytes(reference_bytes))
            reference_file.name = "reference.jpg"

        # Формирование финального промта для OpenAI
        if reference_file:
            prompt = f"""
Первое изображение — главный визуальный референс фотосессии.
Второе изображение — человек клиента.
Перенеси человека со второго изображения в сцену первого изображения.
{prompt_text}
Итог — реалистичная профессиональная фотография. Без пластиковой кожи.
"""
            def generate_image():
                return client.images.edit(
                    model="gpt-image-2",
                    image=[reference_file, image_file],
                    prompt=prompt,
                    size="1024x1536",
                )
        else:
            prompt = prompt_text
            def generate_image():
                return client.images.edit(
                    model="gpt-image-2",
                    image=image_file,
                    prompt=prompt_text,
                    size="1024x1536",
                )

        result = await asyncio.to_thread(generate_image)

        if not result.data or not getattr(result.data[0], "b64_json", None):
            raise RuntimeError("OpenAI returned no image")

        generated_bytes = base64.b64decode(result.data[0].b64_json)
        
        # =======================================================
        # ФИКС ХРАНЕНИЯ: ЖЕСТКОЕ СОХРАНЕНИЕ РЕЗУЛЬТАТА НА ДИСК RENDER
        # =======================================================
        output = io.BytesIO(generated_bytes)
        output.name = f"user_{user_id_str}_res.png"
        
        # Отправляем фото пользователю в чат
        sent_message = await update.message.reply_photo(
            photo=output,
            caption="✨ Твое готовое фото! Надеюсь, тебе понравится ❤️"
        )
        
        # Получаем новый file_id сгенерированной фотографии в Telegram
        tg_file_id = sent_message.photo[-1].file_id
        
        # Записываем физический файл на постоянный диск Render
        local_filename = f"gen_{tg_file_id}.jpg"
        local_photo_path = os.path.join(PHOTOS_DIR, local_filename)
        
        with open(local_photo_path, "wb") as f:
            f.write(generated_bytes)

        # Вызываем функцию сохранения истории (из Шага 2) в prompts.json
        save_photo_to_history(
            photo_id=sent_message.message_id,
            session_key=style or "custom",
            photo_path=local_photo_path,
            tg_file_id=tg_file_id,
            channel_msg_id=None,  # Если будет отправка в канал, обновим этот параметр
            prompt=prompt,
            user_id=update.effective_user.id
        )

        # Списание кредитов / обновление статуса бесплатного использования
        if not is_admin(update):
            if using_paid_credit:
                USERS[user_id_str]["paid_photos"] = max(0, paid_photos - 1)
                save_users(USERS)
            elif using_free_credit:
                FREE_USERS.add(user_id_str)
                save_free_users(FREE_USERS)
                context.user_data["free_used"] = True

        context.user_data.pop("selected_gallery_index", None)
        
    except Exception as e:
        logger.exception("Ошибка в процессе клиентской генерации")
        await update.message.reply_text(f"❌ Произошла ошибка при генерации изображения: {e}")
        # =======================================================
        # ФИКС ХРАНЕНИЯ: ЖЕСТКОЕ СОХРАНЕНИЕ РЕЗУЛЬТАТА НА ДИСК RENDER
        # =======================================================
        output = io.BytesIO(generated_bytes)
        output.name = "ai_photo.png"

        # Отправляем фото пользователю в чат
        sent_message = await update.message.reply_photo(
            photo=output,
            caption=(
                f"✨ Готово!\n\n"
                f"{session['title']}\n\n"
                "Хочешь ещё фото? Выбери другую фотосессию 👇"
            ),
            reply_markup=client_keyboard(),
        )

        # Получаем file_id сгенерированной фотографии
        tg_file_id = sent_message.photo[-1].file_id
        
        # 1. Железно записываем физический файл на постоянный диск Render
        local_filename = f"gen_{tg_file_id}.jpg"
        local_photo_path = os.path.join(PHOTOS_DIR, local_filename)
        
        try:
            with open(local_photo_path, "wb") as f:
                f.write(generated_bytes)

            # 2. Вызываем функцию сохранения истории (из Шага 2) в prompts.json
            save_photo_to_history(
                photo_id=sent_message.message_id,
                session_key=style or "custom",
                photo_path=local_photo_path,
                tg_file_id=tg_file_id,
                channel_msg_id=None,  # Если отправляли в канал, здесь будет id сообщения
                prompt=prompt_text,
                user_id=update.effective_user.id
            )
        except Exception as e:
            logger.error(f"Ошибка при записи файла или промта на диск Render: {e}")

        # Списание кредитов / обновление статуса бесплатного использования
        if not is_admin(update):
            if using_paid_credit:
                if user_id_str in USERS:
                    USERS[user_id_str]["paid_photos"] = max(0, paid_photos - 1)
                    save_users(USERS)
            elif using_free_credit:
                FREE_USERS.add(user_id_str)
                save_free_users(FREE_USERS)
                context.user_data["free_used"] = True

        # Сбрасываем выбор конкретного образа после использования
        context.user_data.pop("selected_gallery_index", None)
        context.user_data.pop("custom_prompt_state", None)
        context.user_data.pop("custom_prompt", None)

    except Exception:
        logger.exception("Image generation error")
        await update.message.reply_text(
            "😔 Не удалось создать фотографию.\n\n"
            "Попробуй отправить фото ещё раз."
        )

# ==========================================
# ХЕНДЛЕР СЛУЧАЙНОГО ТЕКСТА КЛИЕНТА
# ==========================================
async def unknown_text(update, context):
    if is_admin(update) and context.user_data.get("admin_state"):
        return
    await update.message.reply_text("Выбери фотосессию 👇", reply_markup=client_keyboard())

# ==========================================
# 📸 ГЛАВНЫЙ ОБРАБОТЧИК ФОТОГРАФИЙ (ФИКС)
# ==========================================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Единая функция обработки всех изображений. 
    Сохраняет данные на диск Render и защищает от очистки при перезапусках.
    """
    # ------------------------------------------
    # 🛠️ АДМИН: РУЧНОЕ ДОБАВЛЕНИЕ ФОТО В СЕССИЮ
    # ------------------------------------------
    if is_admin(update) and context.user_data.get("admin_state") is not None and context.user_data.get("edit_key") is not None:
        edit_key = context.user_data.get("edit_key")
        
        if not edit_key or edit_key not in SESSIONS:
            context.user_data.clear()
            await update.message.reply_text("❌ Ошибка: фотосессия не найдена.")
            return

        admin_file_id = update.message.photo[-1].file_id
        
        try:
            tg_file = await context.bot.get_file(admin_file_id)
            local_filename = f"admin_{admin_file_id}.jpg"
            local_photo_path = os.path.join(PHOTOS_DIR, local_filename)
            await tg_file.download_to_drive(local_photo_path)
            
            if "gallery_items" not in SESSIONS[edit_key]:
                SESSIONS[edit_key]["gallery_items"] = []
            
            SESSIONS[edit_key]["gallery_items"].append({
                "local_path": local_photo_path,
                "reference_image_file_id": admin_file_id,
                "prompt": SESSIONS[edit_key].get("prompt", "Добавлено вручную через админку"),
                "caption": ""
            })
            
            save_sessions(SESSIONS)
            context.user_data.clear()
            await update.message.reply_text("✅ Фотография успешно добавлена в фотосессию и сохранена на диск!")
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении фото из админки: {e}")
            await update.message.reply_text("❌ Не удалось сохранить файл на диск. Проверьте логи.")
        return

    # ------------------------------------------
    # 📸 КЛИЕНТСКАЯ ГЕНЕРАЦИЯ
    # ------------------------------------------
    custom_prompt = context.user_data.get("custom_prompt") if context.user_data.get("custom_prompt_state") == "waiting_photo" else None
    style = context.user_data.get("selected_style")

    if custom_prompt:
        session = {"title": "✨ Свой промт", "prompt": custom_prompt}
        style = None
    elif not style or style not in SESSIONS:
        await update.message.reply_text(
            "❌ Сначала выбери фотосессию или нажми «СВОЙ ПРОМТ».",
            reply_markup=client_keyboard()
        )
        return
    else:
        session = SESSIONS[style]

    user_id_str = str(update.effective_user.id)
    user_record = USERS.get(user_id_str, {})
    paid_photos = int(user_record.get("paid_photos", 0) or 0)
    has_free = user_id_str in FREE_USERS or bool(context.user_data.get("free_used"))
    using_paid_credit = not is_admin(update) and paid_photos > 0
    using_free_credit = not is_admin(update) and not using_paid_credit and not has_free

    if not is_admin(update) and not using_paid_credit and not using_free_credit:
        await update.message.reply_text(
            "🎁 Бесплатная генерация уже использована.\n\nВыбери пакет фотографий 👇",
            reply_markup=payment_keyboard(),
        )
        return

    await update.message.reply_text(
        "📸 Фото получила!\n\n✨ Начинаю обработку...\nЭто может занять некоторое время."
    )

    try:
        telegram_file = await update.message.photo[-1].get_file()
        photo_bytes = await telegram_file.download_as_bytearray()

        image_file = io.BytesIO(bytes(photo_bytes))
        image_file.name = "photo.jpg"

        gallery_index = context.user_data.get("selected_gallery_index") if style else None
        gallery_items = session.get("gallery_items", [])

        if gallery_index is not None:
            if not (0 <= gallery_index < len(gallery_items)):
                context.user_data.pop("selected_gallery_index", None)
                await update.message.reply_text("❌ Этот образ больше недоступен. Выбери образ ещё раз.")
                return
            selected_item = gallery_items[gallery_index]
            reference_file_id = selected_item.get("reference_image_file_id")
            prompt_text = selected_item.get("prompt") or session.get("prompt", "")
        else:
            reference_file_id = session.get("reference_image_file_id") if style else None
            prompt_text = custom_prompt or session.get("prompt", "")

        reference_file = None
        if reference_file_id:
            try:
                reference_telegram_file = await context.bot.get_file(reference_file_id)
                reference_bytes = await reference_telegram_file.download_as_bytearray()
                reference_file = io.BytesIO(bytes(reference_bytes))
                reference_file.name = "reference.jpg"
            except Exception as e:
                logger.error(f"Не удалось загрузить reference_file_id, пробуем локальный путь: {e}")
                # Подстраховка: если telegram сбросил id, ищем локальный файл на диске
                if gallery_index is not None and "local_path" in gallery_items[gallery_index]:
                    loc_path = gallery_items[gallery_index]["local_path"]
                    if os.path.exists(loc_path):
                        with open(loc_path, "rb") as lf:
                            reference_file = io.BytesIO(lf.read())
                            reference_file.name = "reference.jpg"

        if reference_file:
            prompt = f"""
Первое изображение — главный визуальный референс фотосессии.
Второе изображение — человек клиента.
Перенеси человека со второго изображения в сцену первого изображения.
{prompt_text}
Итог — реалистичная профессиональная фотография. Без пластиковой кожи.
"""
            def generate_image():
                return client.images.edit(
                    model="gpt-image-2",
                    image=[reference_file, image_file],
                    prompt=prompt,
                    size="1024x1536",
                )
        else:
            def generate_image():
                return client.images.edit(
                    model="gpt-image-2",
                    image=image_file,
                    prompt=prompt_text,
                    size="1024x1536",
                )

        result = await asyncio.to_thread(generate_image)

        if not result.data or not getattr(result.data[0], "b64_json", None):
            raise RuntimeError("OpenAI returned no image")

        generated_bytes = base64.b64decode(result.data[0].b64_json)
        
        output = io.BytesIO(generated_bytes)
        output.name = "ai_photo.png"

        sent_message = await update.message.reply_photo(
            photo=output,
            caption=(
                f"✨ Готово!\n\n"
                f"{session['title']}\n\n"
                "Хочешь ещё фото? Выбери другую фотосессию 👇"
            ),
            reply_markup=client_keyboard(),
        )

        # =======================================================
        # СОХРАНЕНИЕ: ЗАПИСЬ НА ФИЗИЧЕСКИЙ ДИСК RENDER
        # =======================================================
        tg_file_id = sent_message.photo[-1].file_id
        local_filename = f"gen_{tg_file_id}.jpg"
        local_photo_path = os.path.join(PHOTOS_DIR, local_filename)
        
        with open(local_photo_path, "wb") as f:
            f.write(generated_bytes)

        # Пишем в prompts.json историю связки фото и промта
        save_photo_to_history(
            photo_id=sent_message.message_id,
            session_key=style or "custom",
            photo_path=local_photo_path,
            tg_file_id=tg_file_id,
            channel_msg_id=None,
            prompt=prompt_text,
            user_id=update.effective_user.id
        )

        if not is_admin(update):
            if using_paid_credit:
                if user_id_str in USERS:
                    USERS[user_id_str]["paid_photos"] = max(0, paid_photos - 1)
                    save_users(USERS)
            elif using_free_credit:
                FREE_USERS.add(user_id_str)
                save_free_users(FREE_USERS)
                context.user_data["free_used"] = True

        context.user_data.pop("selected_gallery_index", None)
        context.user_data.pop("custom_prompt_state", None)
        context.user_data.pop("custom_prompt", None)

    except Exception:
        logger.exception("Image generation error")
        await update.message.reply_text(
            "😔 Не удалось создать фотографию.\n\nПопробуй отправить фото ещё раз."
            )
    
# ==========================================
# РЕГИСТРАЦИЯ ВСЕХ ХЕНДЛЕРОВ ТЕЛЕГРАМ
# ==========================================
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("admin", admin_command))
telegram_app.add_handler(CallbackQueryHandler(callback_handler))

# Главный хендлер для фото (внутри него крутится вся магия photo_handler)
telegram_app.add_handler(
    MessageHandler(filters.PHOTO, photo_handler)
)
# ==========================================
# 👑 ОБРАБОТЧИКИ ТЕКСТОВЫХ СООБЩЕНИЙ (ФИКС)
# ==========================================
async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых команд от администратора в панели управления"""
    if not is_admin(update):
        return
        
    state = context.user_data.get("admin_state")
    
    if state == "waiting_channel_prompt":
        context.user_data["channel_prompt"] = update.message.text
        context.user_data["admin_state"] = "waiting_channel_caption"
        await update.message.reply_text("📢 Теперь отправь текст (описание) для поста в канале:")
        return
        
    if state == "waiting_channel_caption":
        context.user_data["channel_caption"] = update.message.text
        context.user_data["admin_state"] = "channel_photo"
        await update.message.reply_text("📸 Отлично! Теперь отправь исходную фотографию (референс) для генерации поста:")
        return


async def custom_prompt_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода собственного промта пользователем"""
    if context.user_data.get("custom_prompt_state") == "waiting_text":
        context.user_data["custom_prompt"] = update.message.text
        context.user_data["custom_prompt_state"] = "waiting_photo"
        await update.message.reply_text(
            "✨ Твой промт успешно принят!\n\n"
            "📸 Теперь отправь свою фотографию, которую нужно обработать:"
        )
        

# Текстовые хендлеры по группам приоритетов
telegram_app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_admin_channel_flow), group=0)
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, custom_prompt_text_handler), group=1)
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text), group=2)
# ==========================================
# 📢 ЛОГИКА ПОСТА В КАНАЛ И КНОПОК АДМИНА
# ==========================================
async def handle_admin_channel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пошаговый опрос администратора для создания поста в канале"""
    if not is_admin(update):
        return
        
    state = context.user_data.get("admin_state")
    
    # Шаг 3: Ловим промт для клиентов и запрашиваем описание для канала
    if state == "waiting_channel_prompt":
        context.user_data["channel_prompt"] = update.message.text
        context.user_data["admin_state"] = "waiting_channel_caption"
        await update.message.reply_text(
            "✍️ **Шаг 3 из 4**\n\n"
            "Промт принят! Теперь отправь текст **ОПИСАНИЯ (CAPTION)**, который будет написан под самой фотографией в канале (можно использовать хэштеги):"
        )
        return
        
    # Шаг 4: Ловим описание и запрашиваем готовую фотографию референса
    if state == "waiting_channel_caption":
        context.user_data["channel_caption"] = update.message.text
        context.user_data["admin_state"] = "channel_photo"
        await update.message.reply_text(
            "📸 **Шаг 4 из 4**\n\n"
            "Текст поста принят! Теперь отправь **ГОТОВУЮ ФОТОГРАФИЮ**.\n\n"
            "Бот не будет её изменять, он сразу опубликует её в канал с вашей кнопкой «Сделать такое фото»!"
        )
        return

async def handle_admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий админских кнопок для канала"""
    query = update.callback_query
    data = query.data
    
    if data.startswith("admin:"):
        if not is_admin(update):
            await query.message.reply_text("⛔ Доступ ограничен.")
            return
            
        action = data.split(":", 1)[1]
        
        if action == "channel":
            context.user_data.clear()
            buttons = [
                [InlineKeyboardButton(s["title"], callback_data=f"admin_ch_style:{k}")]
                for k, s in SESSIONS.items()
            ]
            await query.message.reply_text(
                "📢 **Шаг 1 из 4**\n\nВыбери фотосессию, к которой будет относиться этот пост в канале 👇",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

    if data.startswith("admin_ch_style:"):
        if not is_admin(update):
            return
        key = data.split(":", 1)[1]
        context.user_data["channel_style"] = key
        context.user_data["admin_state"] = "waiting_channel_prompt"
        
        await query.message.reply_text(
            f"Выбрана сессия: {SESSIONS[key]['title']}\n\n"
            "✍️ **Шаг 2 из 4**\n"
            "Отправь текстовым сообщением **ПРОМТ**, по которому бот будет генерировать фото клиентам, нажавшим кнопку в канале:"
        )
        return
        

# ==========================================
# ЗАПУСК ВЕБХУКА И FASTAPI (LIFESPAN)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Telegram application...")
    await telegram_app.initialize()
    await telegram_app.start()
    
    # Автоматическое определение URL на Render
    render_url = os.environ.get("RENDER_EXTERNAL_URL") or "https://ai-photo-telegram-bot.onrender.com"
    webhook_url = render_url.rstrip("/") + "/telegram"
    
    await telegram_app.bot.set_webhook(webhook_url)
    logger.info("Webhook set: %s", webhook_url)
    logger.info("Telegram application started")
    yield
    logger.info("Stopping Telegram application...")
    
    await telegram_app.stop()
    await telegram_app.shutdown()

app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "ok", "bot": "AI Photo Gallery", "storage": "Render Persistent Disk Connected"}


@app.post("/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
