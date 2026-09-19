
import os
import io
import json
import base64
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ADMIN_ID_RAW = os.environ.get("ADMIN_ID")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@galereyapromt")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "aiphoto_gallery_bot")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-image-2")
KASPI_DETAILS = os.environ.get("KASPI_DETAILS", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")
if not ADMIN_ID_RAW:
    raise RuntimeError("ADMIN_ID is not set")
try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    raise RuntimeError("ADMIN_ID must be a number")

client = OpenAI(api_key=OPENAI_API_KEY)

DATA_DIR = "data"
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
BALANCES_FILE = os.path.join(DATA_DIR, "balances.json")
FREE_USERS_FILE = "free_users.json"
os.makedirs(DATA_DIR, exist_ok=True)

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if data is not None else default
    except Exception:
        logger.exception("Cannot load %s", path)
        return default

def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

DEFAULT_SESSIONS = {
    "autumn": {
        "title": "🍂 Осенняя",
        "prompt": "Создай профессиональную фотореалистичную осеннюю fashion-фотосессию, используя загруженную фотографию человека как строгий референс личности. Максимально точно сохрани идентичность, форму лица, пропорции, глаза, нос, губы, брови, возраст и индивидуальные особенности. Осенняя атмосфера, натуральная золотистая листва, теплые оттенки, красивая композиция, естественная поза, дорогая fashion-съемка, реалистичная кожа с естественной текстурой, детальная одежда и волосы. Профессиональная камера, физически корректный свет, реалистичные тени, кинематографическая глубина резкости. Высокий фотореализм. Без пластиковой кожи, beauty-фильтров, изменения лица, CGI и мультяшности.",
        "items": []
    },
    "luxury": {
        "title": "💎 Luxury",
        "prompt": "Создай роскошную профессиональную fashion-фотографию человека на основе загруженного изображения. Максимально точно сохрани личность, лицо, возраст, пропорции и индивидуальные особенности. Эстетика luxury editorial: премиальная атмосфера, изысканный интерьер, элегантная одежда, дорогие фактуры и стильная композиция. Профессиональная журнальная фотосъемка, реалистичная кожа, естественная текстура, детальная ткань и волосы, мягкий направленный свет, естественные тени, профессиональная оптика. Очень высокий фотореализм. Без пластиковой кожи, beauty-фильтров, изменения личности, CGI и мультяшности.",
        "items": []
    },
    "fashion": {
        "title": "👠 Fashion",
        "prompt": "Создай современную профессиональную fashion editorial фотографию на основе загруженного изображения человека. Сохрани идентичность максимально точно, не изменяй черты лица, возраст, пропорции и индивидуальные особенности. Стиль современной fashion editorial съемки: уверенная естественная поза, динамичная композиция, стильная одежда, дорогой fashion-образ и профессиональная постановка. Реалистичная кожа, детальная ткань, волосы, руки и пальцы. Профессиональный свет, объемные тени, реалистичная оптика и глубина резкости. Максимальный фотореализм без пластиковой кожи, CGI и мультяшности.",
        "items": []
    },
    "love": {
        "title": "❤️ Love Story",
        "prompt": "Создай романтическую профессиональную фотографию в стиле Love Story на основе загруженного изображения. Если на референсе один человек, сохрани его идентичность максимально точно. Если присутствуют два человека, сохрани идентичность каждого. Не изменяй лица, возраст и пропорции. Теплая романтическая атмосфера, естественные эмоции, живое взаимодействие, кинематографическая композиция, красивый естественный фон. Профессиональная фотосъемка, мягкий естественный свет, реалистичная кожа, натуральная текстура, детальная одежда и волосы. Высокий фотореализм без пластиковой кожи, beauty-фильтров, изменения лиц, CGI и мультяшности.",
        "items": []
    },
    "romantic": {
        "title": "🌸 Romantic",
        "prompt": "Создай нежную романтическую fashion-фотографию на основе загруженного изображения человека. Сохрани идентичность человека максимально точно, включая лицо, возраст, форму лица и индивидуальные особенности. Нежная романтическая атмосфера, элегантный образ, мягкие детали, естественная поза, воздушная композиция. Профессиональная editorial фотосъемка, мягкий объемный свет, реалистичная кожа с естественной текстурой, реалистичные волосы и ткани, физически корректное освещение. Максимальный фотореализм без пластиковой кожи, изменения лица, CGI и мультяшности.",
        "items": []
    },
    "black": {
        "title": "🖤 Black Editorial",
        "prompt": "Создай профессиональную драматичную fashion editorial фотографию на основе загруженного изображения человека. Максимально точно сохрани личность, лицо, возраст, пропорции и индивидуальные особенности. Черная эстетика editorial: темный стиль, элегантная одежда, минималистичная композиция, выразительная поза и дорогая fashion-атмосфера. Контрастный профессиональный свет, естественные тени, кинематографическая глубина, реалистичная кожа и фактура одежды, дорогая оптика. Максимальный фотореализм без изменения лица, пластиковой кожи, beauty-фильтров, CGI и мультяшности.",
        "items": []
    },
    "child": {
        "title": "👶 Детская фотосессия",
        "prompt": "Создай профессиональную детскую фотосессию на основе загруженной фотографии ребенка. Максимально точно сохрани внешность, идентичность, возраст, лицо, пропорции и индивидуальные особенности ребенка. Создай красивую профессиональную фотосессию, естественную детскую позу и живые эмоции. Мягкий красивый свет, естественная кожа с натуральной текстурой, реалистичные волосы и одежда, профессиональная композиция. Настоящая фотография профессионального детского фотографа. Без изменения внешности, мультяшности и CGI.",
        "items": []
    },
    "man": {
        "title": "🤵 Мужская фотосессия",
        "prompt": "Создай профессиональную мужскую fashion-фотосессию на основе загруженной фотографии. Максимально точно сохрани личность, внешность, лицо, возраст, пропорции, глаза, нос, губы, бороду и индивидуальные особенности. Стиль современной мужской editorial фотосъемки: уверенная естественная поза, дорогой мужской образ, стильная одежда и профессиональная композиция. Реалистичная кожа, детальная одежда, волосы и борода. Профессиональное освещение, естественные тени, кинематографическая глубина резкости и дорогая оптика. Максимальный фотореализм без изменения лица, CGI и мультяшности.",
        "items": []
    },
    "winter": {
        "title": "❄️ Зимние образы",
        "prompt": "Создай профессиональную зимнюю fashion editorial фотосессию на основе загруженной фотографии. Строго сохрани личность, лицо, возраст, пропорции и индивидуальные особенности человека. Современный зимний образ, выразительная фактура теплой одежды, снег, стильная зимняя локация, кинематографический свет, реалистичные материалы и естественная кожа. Профессиональная журнальная фотография, реалистичные тени и глубина. Без изменения лица, пластиковой кожи, CGI и мультяшности.",
        "items": []
    },
    "author": {
        "title": "✨ Авторский промт",
        "prompt": "Создай авторскую профессиональную editorial-фотографию на основе загруженной фотографии человека. Сохрани личность, лицо, возраст и индивидуальные особенности максимально точно. Сделай необычную современную визуальную концепцию с сильным художественным акцентом, премиальной fashion-эстетикой, кинематографическим светом, выразительной композицией и фотореалистичной детализацией. Изображение должно выглядеть как работа профессионального фотографа и арт-директора, а не как случайная AI-картинка.",
        "items": []
    },
    "couples": {
        "title": "💞 Парные фото",
        "prompt": "Создай профессиональную парную фотографию на основе загруженного изображения или изображений. Строго сохрани идентичность каждого человека, лица, возраст и естественные пропорции. Создай естественное взаимодействие, гармоничную композицию, современный стиль и живые эмоции. Профессиональный свет, реалистичная кожа, волосы, одежда и руки, физически корректные тени и перспектива. Высокий фотореализм без изменения лиц, CGI и мультяшности.",
        "items": []
    },
    "women_portrait": {
        "title": "👩 Портреты женские",
        "prompt": "Создай профессиональный женский портрет на основе загруженной фотографии. Строго сохрани лицо, возраст, пропорции и узнаваемость человека. Эстетика high-end beauty и fashion editorial, выразительная композиция, профессиональный свет, натуральная текстура кожи, реалистичные волосы, глаза и ткань. Дорогая журнальная фотография, физически корректный свет и тени, высокая детализация. Без изменения лица, пластиковой кожи, beauty-фильтров, CGI и мультяшности.",
        "items": []
    },
    "men_portrait": {
        "title": "👨 Портреты мужские",
        "prompt": "Создай профессиональный мужской портрет на основе загруженной фотографии. Строго сохрани лицо, возраст, пропорции, волосы, бороду и узнаваемость человека. Современная мужская editorial-эстетика, выразительный свет, реалистичная кожа, волосы, одежда и детали. Профессиональная камера, естественные тени, реалистичная перспектива и высокая детализация. Без изменения лица, пластиковой кожи, CGI и мультяшности.",
        "items": []
    },
    "studio": {
        "title": "🎬 Студийные фото",
        "prompt": "Создай профессиональную студийную фотографию на основе загруженного изображения человека. Строго сохрани личность, лицо, возраст и пропорции. Премиальная студийная постановка, профессиональный фон, тщательно выставленный свет, естественная кожа, реалистичные волосы и одежда, точные тени и объем. Эстетика high-end commercial photography, photorealism, editorial quality. Без изменения лица, пластиковой кожи, CGI и мультяшности.",
        "items": []
    },
    "stickers": {
        "title": "🎀 Стикеры",
        "prompt": "Создай набор выразительных реалистичных sticker-style изображений на основе загруженной фотографии человека, сохраняя узнаваемость, лицо и индивидуальные особенности. Чистая композиция, аккуратный контур, выразительная поза и эмоция, профессиональная детализация. Не менять личность человека.",
        "items": []
    },
    "humor": {
        "title": "😂 Юмористические фото",
        "prompt": "Создай яркую фотореалистичную юмористическую сцену на основе загруженной фотографии человека. Строго сохрани личность, лицо, возраст и пропорции. Сделай ситуацию необычной, смешной и визуально выразительной, но реалистичной: естественная анатомия, руки, одежда, свет и перспектива. Профессиональная постановочная фотография с четкой визуальной идеей. Без изменения лица, CGI и мультяшности.",
        "items": []
    },
}

SESSIONS = load_json(SESSIONS_FILE, DEFAULT_SESSIONS)
for key, value in DEFAULT_SESSIONS.items():
    if key not in SESSIONS:
        SESSIONS[key] = value
    SESSIONS[key].setdefault("items", [])

BALANCES = load_json(BALANCES_FILE, {})
FREE_USERS = set(load_json(FREE_USERS_FILE, [5431086812]))
save_json(FREE_USERS_FILE, sorted(FREE_USERS))
save_json(SESSIONS_FILE, SESSIONS)

def save_sessions():
    save_json(SESSIONS_FILE, SESSIONS)

def save_balances():
    save_json(BALANCES_FILE, BALANCES)

def is_admin(update):
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)

def is_unlimited(update):
    return is_admin(update) or update.effective_user.id in FREE_USERS

def paid_count(uid):
    return int(BALANCES.get(str(uid), 0))

def generation_allowed(update, context):
    if is_unlimited(update):
        return True
    return not context.user_data.get("free_used", False) or paid_count(update.effective_user.id) > 0

def consume_generation(update, context):
    if is_unlimited(update):
        return
    uid = str(update.effective_user.id)
    if context.user_data.get("free_used", False):
        BALANCES[uid] = max(0, paid_count(update.effective_user.id) - 1)
        save_balances()
    else:
        context.user_data["free_used"] = True

def client_keyboard():
    keys = list(SESSIONS.keys())
    rows = []
    for i in range(0, len(keys), 2):
        rows.append([
            InlineKeyboardButton(SESSIONS[k]["title"], callback_data=f"style:{k}")
            for k in keys[i:i+2]
        ])
    rows.append([InlineKeyboardButton("✍️ СВОЙ ПРОМТ", callback_data="custom")])
    return InlineKeyboardMarkup(rows)

def payment_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 ПОКАЗАТЬ РЕКВИЗИТЫ", callback_data="details")],
        [InlineKeyboardButton("💰 КУПИТЬ ФОТО", callback_data="packages")],
        [InlineKeyboardButton("⬅️ В МЕНЮ", callback_data="menu")],
    ])

def packages_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 фото — 500 ₸", callback_data="buy:1:500")],
        [InlineKeyboardButton("3 фото — 1 200 ₸", callback_data="buy:3:1200")],
        [InlineKeyboardButton("5 фото — 1 800 ₸ ⭐", callback_data="buy:5:1800")],
        [InlineKeyboardButton("10 фото — 3 000 ₸", callback_data="buy:10:3000")],
        [InlineKeyboardButton("⬅️ НАЗАД", callback_data="menu")],
    ])

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить фотосессию", callback_data="admin:add")],
        [InlineKeyboardButton("✏️ Изменить промт", callback_data="admin:edit")],
        [InlineKeyboardButton("🗑 Удалить фотосессию", callback_data="admin:delete")],
        [InlineKeyboardButton("📢 Пост в канал", callback_data="admin:channel")],
        [InlineKeyboardButton("📋 Мои фотосессии", callback_data="admin:list")],
        [InlineKeyboardButton("📸 Добавить фото в фотосессию", callback_data="admin:addphoto")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="admin:home")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    payload = context.args[0] if context.args else ""
    if payload.startswith("item_"):
        parts = payload.split("_", 2)
        if len(parts) == 3 and parts[1] in SESSIONS:
            try:
                return await show_item(update, context, parts[1], int(parts[2]))
            except ValueError:
                pass
    if payload in SESSIONS:
        context.user_data["selected_style"] = payload
        await update.message.reply_text(
            f"✨ Выбрана фотосессия:\n\n{SESSIONS[payload]['title']}\n\n"
            "📸 Теперь просто отправь свою фотографию.\n"
            "Промт писать не нужно — всё уже подготовлено мной 💫"
        )
        return
    await update.message.reply_text(
        "✨ *Добро пожаловать в AI PHOTO STUDIO*\n\n"
        "Здесь обычная фотография превращается в профессиональную фотосессию 📸\n\n"
        "🌸 Выбирай понравившийся образ\n"
        "📷 Загружай свою фотографию\n"
        "✨ Получай готовый результат\n\n"
        "*Промт писать не нужно* — всё уже подготовлено мной 💫\n\n"
        "🎁 *Первая фотография — бесплатная*\n\n"
        "Готова? Тогда выбирай свою фотосессию 👇",
        parse_mode="Markdown",
        reply_markup=client_keyboard(),
    )

async def admin_command(update, context):
    if not is_admin(update):
        await update.message.reply_text("⛔ У вас нет доступа к админ-панели.")
        return
    context.user_data.clear()
    await update.message.reply_text("👑 Панель администратора\n\nВыбери действие:", reply_markup=admin_keyboard())

async def show_item(update, context, key, idx):
    items = SESSIONS.get(key, {}).get("items", [])
    if idx < 0 or idx >= len(items):
        target = update.callback_query.message if update.callback_query else update.message
        await target.reply_text("❌ Образ не найден.")
        return
    context.user_data["selected_style"] = key
    context.user_data["selected_item"] = idx
    item = items[idx]
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 СДЕЛАТЬ ФОТО", callback_data=f"make:{key}:{idx}")],
        [InlineKeyboardButton("⬅️ К ФОТОСЕССИЯМ", callback_data="menu")],
    ])
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_photo(item["file_id"], caption=item.get("caption") or SESSIONS[key]["title"], reply_markup=markup)

async def show_style(query, context, key):
    if key not in SESSIONS:
        await query.message.reply_text("❌ Фотосессия не найдена.")
        return
    context.user_data["selected_style"] = key
    items = SESSIONS[key].get("items", [])
    if not items:
        await query.message.reply_text(
            f"{SESSIONS[key]['title']}\n\nПока здесь нет готовых образов.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ В МЕНЮ", callback_data="menu")]])
        )
        return
    for idx, item in enumerate(items):
        await query.message.reply_photo(
            item["file_id"],
            caption=item.get("caption") or SESSIONS[key]["title"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📸 СДЕЛАТЬ ФОТО", callback_data=f"make:{key}:{idx}")]
            ])
        )
    await query.message.reply_text("Выбери образ 👆", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ В МЕНЮ", callback_data="menu")]
    ]))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    await query.answer()

    if data == "menu":
        await query.message.reply_text("📸 Выбирай фотосессию 👇", reply_markup=client_keyboard())
        return

    if data == "custom":
        context.user_data["mode"] = "custom_prompt"
        await query.message.reply_text(
            "✍️ *СВОЙ ПРОМТ*\n\n"
            "Отправь свой промт одним сообщением.\n"
            "После этого я попрошу твоё фото и сразу сделаю генерацию.",
            parse_mode="Markdown"
        )
        return

    if data.startswith("style:"):
        await show_style(query, context, data.split(":", 1)[1])
        return

    if data.startswith("make:"):
        _, key, idx = data.split(":")
        if key not in SESSIONS:
            await query.message.reply_text("❌ Образ не найден.")
            return
        context.user_data["mode"] = "gallery"
        context.user_data["selected_style"] = key
        context.user_data["selected_item"] = int(idx)
        if not generation_allowed(update, context):
            await query.message.reply_text(
                "🎁 Бесплатная генерация уже использована.\n\nВыбери пакет фотографий 👇",
                reply_markup=payment_keyboard()
            )
            return
        await query.message.reply_text("📷 Теперь загрузи свою фотографию.")
        return

    if data == "details":
        details = KASPI_DETAILS or "Реквизиты пока не указаны в Render."
        await query.message.reply_text(
            f"💳 *Реквизиты для оплаты:*\n\n{details}",
            parse_mode="Markdown",
            reply_markup=packages_keyboard()
        )
        return

    if data == "packages":
        await query.message.reply_text("💰 Выбери пакет:", reply_markup=packages_keyboard())
        return

    if data.startswith("buy:"):
        _, count, price = data.split(":")
        context.user_data["pending_package"] = {"count": int(count), "price": int(price)}
        await query.message.reply_text(
            f"💳 Пакет: *{count} фото — {price} ₸*\n\n"
            "После оплаты нажми кнопку ниже.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Я оплатил(а)", callback_data="paid")],
                [InlineKeyboardButton("⬅️ К ПАКЕТАМ", callback_data="packages")],
            ])
        )
        return

    if data == "paid":
        package = context.user_data.get("pending_package")
        if not package:
            await query.message.reply_text("Сначала выбери пакет.", reply_markup=packages_keyboard())
            return
        await context.bot.send_message(
            ADMIN_ID,
            f"💳 Запрос на подтверждение оплаты\n"
            f"Пользователь: {update.effective_user.id}\n"
            f"Пакет: {package['count']} фото — {package['price']} ₸",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✅ НАЧИСЛИТЬ",
                    callback_data=f"adminpay:{update.effective_user.id}:{package['count']}"
                )
            ]])
        )
        await query.message.reply_text("⏳ Запрос отправлен администратору. После подтверждения фото будут доступны.")
        return

    if data.startswith("adminpay:") and is_admin(update):
        _, uid, count = data.split(":")
        BALANCES[uid] = paid_count(int(uid)) + int(count)
        save_balances()
        await query.message.reply_text(f"✅ Начислено {count} фото пользователю {uid}.")
        try:
            await context.bot.send_message(int(uid), f"✅ Оплата подтверждена.\nНачислено фото: {count}.")
        except Exception:
            logger.exception("Cannot notify user")
        return

    if not is_admin(update):
        return

    if data == "admin:home":
        context.user_data.clear()
        await query.message.reply_text("👑 Панель администратора", reply_markup=admin_keyboard())
        return

    if data == "admin:add":
        context.user_data.clear()
        context.user_data["admin_state"] = "add_title"
        await query.message.reply_text("➕ Напиши название новой фотосессии.")
        return
    if data == "admin:addphoto":
        buttons = [
            [InlineKeyboardButton(
                session["title"],
                callback_data=f"addphoto:{key}"
            )]
            for key, session in SESSIONS.items()
        ]

        buttons.append([
            InlineKeyboardButton(
                "⬅️ НАЗАД",
                callback_data="admin:home"
            )
        ])

        await query.message.reply_text(
            "📸 Выбери фотосессию, куда добавить фото:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return    
    if data == "admin:channel":
        buttons = [[InlineKeyboardButton(s["title"], callback_data=f"channel_style:{k}")] for k, s in SESSIONS.items()]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="admin:home")])
        await query.message.reply_text("📢 Выбери фотосессию для нового образа:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data == "admin:list":
        text = "📋 *Фотосессии:*\n\n" + "\n".join(
            f"• {s['title']} — {len(s.get('items', []))} образов"
            for s in SESSIONS.values()
        )
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=admin_keyboard())
        return

    if data == "admin:edit":
        buttons = [[InlineKeyboardButton(s["title"], callback_data=f"edit:{k}")] for k, s in SESSIONS.items()]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="admin:home")])
        await query.message.reply_text("✏️ Выбери фотосессию:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data == "admin:delete":
        buttons = [[InlineKeyboardButton(f"🗑 {s['title']}", callback_data=f"delete:{k}")] for k, s in SESSIONS.items()]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="admin:home")])
        await query.message.reply_text("🗑 Выбери фотосессию:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("channel_style:"):
        key = data.split(":", 1)[1]
        context.user_data["admin_state"] = "channel_caption"
        context.user_data["channel_style"] = key
        await query.message.reply_text(f"📢 Пост для {SESSIONS[key]['title']}\n\nНапиши текст поста.")
        return
        if data.startswith("addphoto:"):
        key = data.split(":", 1)[1]

        if key not in SESSIONS:
            await query.message.reply_text(
                "❌ Фотосессия не найдена.",
                reply_markup=admin_keyboard()
            )
            return

        context.user_data["admin_state"] = "add_photo_prompt"
        context.user_data["add_photo_key"] = key

        await query.message.reply_text(
            f"📸 Добавление фото в: {SESSIONS[key]['title']}\n\n"
            "Шаг 1. Отправь промт для этого фото."
        )
        return
    if data.startswith("edit:"):
        key = data.split(":", 1)[1]
        context.user_data["admin_state"] = "edit_prompt"
        context.user_data["edit_key"] = key
        await query.message.reply_text("✏️ Отправь новый промт.")
        return

    if data.startswith("delete:"):
        key = data.split(":", 1)[1]
        title = SESSIONS[key]["title"]
        del SESSIONS[key]
        save_sessions()
        await query.message.reply_text(f"🗑 Удалено: {title}", reply_markup=admin_keyboard())
        return

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()

    if is_admin(update) and context.user_data.get("admin_state"):
        state = context.user_data["admin_state"]
        if state == "channel_caption":
            context.user_data["channel_caption"] = text
            context.user_data["admin_state"] = "channel_prompt"
            await update.message.reply_text("✨ Теперь отправь промт для этого образа.")
            return
        if state == "channel_prompt":
            context.user_data["channel_prompt"] = text
            context.user_data["admin_state"] = "channel_photo"
            await update.message.reply_text("📸 Теперь отправь фото для образа.")
            return
        if state == "add_title":
            context.user_data["new_title"] = text
            context.user_data["admin_state"] = "add_prompt"
            await update.message.reply_text("Теперь отправь промт для новой фотосессии.")
            return
        if state == "add_prompt":
            n = 1
            while f"custom_{n}" in SESSIONS:
                n += 1
            SESSIONS[f"custom_{n}"] = {"title": context.user_data["new_title"], "prompt": text, "items": []}
            save_sessions()
            context.user_data.clear()
            await update.message.reply_text("✅ Фотосессия создана.", reply_markup=admin_keyboard())
            return
        if state == "edit_prompt":
            key = context.user_data.get("edit_key")
            if key in SESSIONS:
                SESSIONS[key]["prompt"] = text
                save_sessions()
                context.user_data.clear()
                await update.message.reply_text("✅ Промт обновлён.", reply_markup=admin_keyboard())
            return
        if state == "add_photo_prompt":
            key = context.user_data.get("add_photo_key")

            if key not in SESSIONS:
                context.user_data.clear()
                await update.message.reply_text(
                    "❌ Фотосессия не найдена.",
                    reply_markup=admin_keyboard(),
                )
                return

            context.user_data["add_photo_prompt"] = text
            context.user_data["admin_state"] = "add_photo_photo"

            await update.message.reply_text(
                "📸 Шаг 2. Отправь фото.\n\n"
                "Оно будет сохранено только в фотосессии "
                "и не будет опубликовано в канале."
            )
            return
    if context.user_data.get("mode") == "custom_prompt":
        context.user_data["custom_prompt"] = text
        context.user_data["mode"] = "custom_photo"
        if not generation_allowed(update, context):
            await update.message.reply_text(
                "🎁 Бесплатная генерация уже использована.\n\nВыбери пакет фотографий 👇",
                reply_markup=payment_keyboard()
            )
            return
        await update.message.reply_text("📷 Теперь загрузи свою фотографию.")
        return

    await update.message.reply_text("Выбери действие в меню 👇", reply_markup=client_keyboard())

async def generate_image(user_bytes, prompt, reference_bytes=None):
    def run():
        user_file = io.BytesIO(user_bytes)
        user_file.name = "user.jpg"
        files = [user_file]
        if reference_bytes:
            ref_file = io.BytesIO(reference_bytes)
            ref_file.name = "reference.jpg"
            files.append(ref_file)
        try:
            result = client.images.edit(
                model=OPENAI_MODEL,
                image=files if len(files) > 1 else files[0],
                prompt=prompt,
                size="1024x1536",
            )
            return result
        finally:
            for f in files:
                f.close()
    return await asyncio.to_thread(run)

async def process_generation(update, context, prompt, reference_file_id=None):
    if not generation_allowed(update, context):
        await update.message.reply_text(
            "🎁 Бесплатная генерация уже использована.\n\nВыбери пакет фотографий 👇",
            reply_markup=payment_keyboard()
        )
        return

    tg_file = await update.message.photo[-1].get_file()
    user_bytes = bytes(await tg_file.download_as_bytearray())

    reference_bytes = None
    if reference_file_id:
        ref_file = await context.bot.get_file(reference_file_id)
        reference_bytes = bytes(await ref_file.download_as_bytearray())

    await update.message.reply_text("✨ Создаю фото... Это может занять немного времени.")
    try:
        result = await generate_image(user_bytes, prompt, reference_bytes)
        if not result.data or not getattr(result.data[0], "b64_json", None):
            raise RuntimeError("OpenAI returned no image")
        generated = base64.b64decode(result.data[0].b64_json)
        output = io.BytesIO(generated)
        output.name = "ai_photo.png"
        consume_generation(update, context)
        await update.message.reply_photo(
            photo=output,
            caption="✨ Готово! Вот твой результат 📸",
            reply_markup=client_keyboard()
        )
    except Exception:
        logger.exception("Image generation error")
        await update.message.reply_text("😔 Не удалось создать фотографию. Попробуй ещё раз.")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if is_admin(update) and context.user_data.get("admin_state") == "add_photo_photo":
        key = context.user_data.get("add_photo_key")
        prompt = context.user_data.get("add_photo_prompt", "")

        if key not in SESSIONS:
            context.user_data.clear()
            await update.message.reply_text(
                "❌ Фотосессия не найдена.",
                reply_markup=admin_keyboard(),
            )
            return

        photo_id = update.message.photo[-1].file_id

        item = {
            "file_id": photo_id,
            "prompt": prompt,
            "caption": SESSIONS[key]["title"],
        }

        SESSIONS[key].setdefault("items", []).append(item)
        index = len(SESSIONS[key]["items"]) - 1

        save_sessions()
        context.user_data.clear()

        await update.message.reply_text(
            f"✅ Фото добавлено в фотосессию "
            f"«{SESSIONS[key]['title']}».\n\n"
            f"📸 Кадр №{index + 1} сохранён.\n"
            "📢 В канал ничего не опубликовано.",
            reply_markup=admin_keyboard(),
        )
        return
    if is_admin(update) and context.user_data.get("admin_state") == "channel_photo":
        key = context.user_data.get("channel_style")
        caption = context.user_data.get("channel_caption", "")
        prompt = context.user_data.get("channel_prompt", "")
        if not key or key not in SESSIONS:
            context.user_data.clear()
            await update.message.reply_text("❌ Фотосессия не найдена.", reply_markup=admin_keyboard())
            return

        item = {
            "file_id": update.message.photo[-1].file_id,
            "prompt": prompt,
            "caption": caption,
        }
        SESSIONS[key].setdefault("items", []).append(item)
        idx = len(SESSIONS[key]["items"]) - 1
        save_sessions()

        button = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "📸 СДЕЛАТЬ ФОТО",
                url=f"https://t.me/{BOT_USERNAME}?start=item_{key}_{idx}"
            )
        ]])
        try:
            await context.bot.send_photo(
                chat_id=CHANNEL_USERNAME,
                photo=item["file_id"],
                caption=caption,
                reply_markup=button
            )
            context.user_data.clear()
            await update.message.reply_text("✅ Образ сохранён в галерее и опубликован в канале.", reply_markup=admin_keyboard())
        except Exception:
            logger.exception("Channel post error")
            await update.message.reply_text("❌ Не удалось опубликовать пост. Проверь права бота в канале.")
        return

    mode = context.user_data.get("mode")
    if mode == "gallery":
        key = context.user_data.get("selected_style")
        idx = context.user_data.get("selected_item")
        try:
            item = SESSIONS[key]["items"][idx]
        except Exception:
            await update.message.reply_text("❌ Образ не найден. Выбери его заново.", reply_markup=client_keyboard())
            return
        await process_generation(update, context, item["prompt"], item["file_id"])
        return

    if mode == "custom_photo":
        await process_generation(update, context, context.user_data.get("custom_prompt", ""), None)
        return

    await update.message.reply_text("Сначала выбери фотосессию 👇", reply_markup=client_keyboard())

async def unknown_command(update, context):
    await update.message.reply_text("Выбери действие в меню 👇", reply_markup=client_keyboard())

telegram_app = Application.builder().token(BOT_TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("admin", admin_command))
telegram_app.add_handler(CallbackQueryHandler(callback_handler))
telegram_app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
telegram_app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

@asynccontextmanager
async def lifespan(app):
    logger.info("Starting Telegram application...")
    await telegram_app.initialize()
    await telegram_app.start()
    render_url = os.environ.get("RENDER_EXTERNAL_URL") or "https://ai-photo-telegram-bot.onrender.com"
    webhook_url = render_url.rstrip("/") + "/telegram"
    await telegram_app.bot.set_webhook(webhook_url)
    logger.info("Telegram application started")
    yield
    try:
        await telegram_app.bot.delete_webhook()
    except Exception:
        logger.exception("Could not delete webhook")
    await telegram_app.stop()
    await telegram_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def health():
    return {"status": "ok", "bot": "AI Photo Gallery"}

@app.post("/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "10000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
