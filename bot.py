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
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ADMIN_ID = os.environ.get("ADMIN_ID")
CHANNEL_USERNAME = "@galereyapromt"
BOT_USERNAME = "aiphoto_gallery_bot"

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
    "autumn": {"title": "🍂 Осенняя", "prompt": """
Создай профессиональную фотореалистичную осеннюю fashion-фотосессию, используя загруженную фотографию человека как строгий референс личности.
Максимально точно сохрани идентичность человека: форму лица, пропорции, глаза, нос, губы, брови и индивидуальные особенности. Не меняй возраст и внешность человека.
Осенняя атмосфера, натуральная золотистая листва, теплые оттенки, красивая композиция, естественная поза, живое движение, дорогая fashion-съемка, реалистичная кожа с естественной текстурой, детальная одежда и волосы.
Профессиональная камера, физически корректный свет, мягкий естественный объемный свет, реалистичные тени, кинематографическая глубина резкости.
Фотореализм высокого уровня. Без пластиковой кожи, без чрезмерного сглаживания, без изменения лица, без эффекта CGI, без мультяшности.
"""},
    "luxury": {"title": "💎 Luxury", "prompt": """
Создай роскошную профессиональную fashion-фотографию человека на основе загруженного изображения.
Максимально точно сохрани личность и черты лица человека. Не меняй форму лица, пропорции, глаза, нос, губы, брови и индивидуальные особенности внешности.
Эстетика luxury editorial: дорогой образ, премиальная атмосфера, изысканный интерьер, элегантная одежда, дорогие фактуры, стильная композиция.
Профессиональная журнальная фотосъемка, реалистичная кожа, естественная текстура кожи, детальная ткань, реалистичные волосы.
Мягкий направленный студийный свет, глубокие естественные тени, красивый объем, профессиональная оптика, малая глубина резкости.
Очень высокий фотореализм. Без пластиковой кожи, beauty-фильтров, изменения личности, CGI и мультяшного эффекта.
"""},
    "fashion": {"title": "👠 Fashion", "prompt": """
Создай современную профессиональную fashion-фотографию на основе загруженного изображения человека.
Сохрани идентичность человека максимально точно. Не изменяй черты лица, пропорции и индивидуальные особенности.
Стиль современной fashion editorial съемки: уверенная поза, динамичная композиция, стильная одежда, дорогой fashion-образ, профессиональная постановка.
Изображение должно выглядеть как настоящая съемка профессионального fashion-фотографа.
Реалистичная кожа с естественной текстурой, детальная ткань, реалистичные волосы, естественные руки и пальцы.
Профессиональный свет, объемные тени, реалистичная оптика, естественная глубина резкости.
Максимальный фотореализм. Не использовать пластиковую кожу, чрезмерное сглаживание, CGI или мультяшность.
"""},
    "love": {"title": "❤️ Love Story", "prompt": """
Создай романтическую профессиональную фотографию в стиле Love Story на основе загруженного изображения.
Если на референсе один человек, сохрани его идентичность максимально точно. Если присутствуют два человека, сохрани идентичность каждого.
Не изменяй черты лица, пропорции и индивидуальные особенности.
Теплая романтическая атмосфера, естественные эмоции, живое взаимодействие, кинематографическая композиция, красивый естественный фон.
Профессиональная фотосъемка, мягкий естественный свет, реалистичная кожа, натуральная текстура, детальная одежда и волосы.
Фотореализм высокого уровня. Без пластиковой кожи, beauty-фильтров, изменения лиц, CGI и мультяшности.
"""},
    "romantic": {"title": "🌸 Romantic", "prompt": """
Создай нежную романтическую fashion-фотографию на основе загруженного изображения человека.
Сохрани идентичность человека максимально точно. Не изменяй форму лица, глаза, нос, губы, брови и другие индивидуальные особенности.
Нежная романтическая атмосфера, элегантный образ, мягкие детали, естественная поза, воздушная композиция.
Профессиональная editorial фотосъемка, мягкий объемный свет, реалистичная кожа с естественной текстурой, реалистичные волосы и ткани.
Красивое естественное боке, профессиональная оптика, физически корректное освещение.
Максимальный фотореализм. Без пластиковой кожи, чрезмерного сглаживания, изменения лица, CGI и мультяшности.
"""},
    "black": {"title": "🖤 Black Editorial", "prompt": """
Создай профессиональную драматичную fashion editorial фотографию на основе загруженного изображения человека.
Максимально точно сохрани личность человека, его лицо, пропорции и индивидуальные особенности.
Черная эстетика editorial: темный стиль, элегантная одежда, минималистичная композиция, выразительная поза, дорогая fashion-атмосфера.
Контрастный профессиональный свет, объемные естественные тени, кинематографическая глубина, реалистичная кожа и фактура одежды.
Профессиональная full-frame камера, дорогая оптика, реалистичная глубина резкости.
Максимальный фотореализм. Без изменения лица, пластиковой кожи, beauty-фильтров, CGI и мультяшности.
"""},
    "child": {"title": "👶 Детская фотосессия", "prompt": """
Создай профессиональную детскую фотосессию на основе загруженной фотографии ребенка.
Максимально точно сохрани внешность и идентичность ребенка. Не изменяй лицо, форму глаз, нос, губы, пропорции лица и индивидуальные особенности.
Создай красивую профессиональную фотосессию, естественную детскую позу и живые эмоции.
Мягкий красивый свет, естественная кожа с натуральной текстурой, реалистичные волосы и одежда, профессиональная композиция.
Изображение должно выглядеть как настоящая фотография, снятая профессиональным детским фотографом.
Без пластиковой кожи, без изменения внешности, без мультяшности и CGI.
"""},
    "man": {"title": "🤵 Мужская фотосессия", "prompt": """
Создай профессиональную мужскую fashion-фотосессию на основе загруженной фотографии.
Максимально точно сохрани личность и внешность мужчины. Не изменяй лицо, пропорции, глаза, нос, губы, бороду и индивидуальные особенности.
Стиль современной мужской editorial фотосъемки: уверенная естественная поза, дорогой мужской образ, стильная одежда, профессиональная композиция.
Реалистичная кожа с естественной текстурой, детальная одежда, реалистичные волосы и борода.
Профессиональное освещение, объемные естественные тени, кинематографическая глубина резкости, дорогая оптика.
Максимальный фотореализм. Без пластиковой кожи, beauty-фильтров, изменения лица, CGI и мультяшного эффекта.
"""},
}

PROMPTS_FILE = "prompts.json"

def save_sessions(data):
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_sessions():
    if not os.path.exists(PROMPTS_FILE):
        save_sessions(DEFAULT_SESSIONS)
        return DEFAULT_SESSIONS.copy()
    try:
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            save_sessions(DEFAULT_SESSIONS)
            return DEFAULT_SESSIONS.copy()
        return data
    except Exception as e:
        logger.error("Error loading prompts.json: %s", e)
        return DEFAULT_SESSIONS.copy()

SESSIONS = load_sessions()
telegram_app = Application.builder().token(BOT_TOKEN).build()

def client_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(s["title"], callback_data=f"style:{k}")]
        for k, s in SESSIONS.items()
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
    return bool(update.effective_user and update.effective_user.id == ADMIN_ID)

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
        await query.message.reply_text(
            f"{SESSIONS[key]['title']}\n\nОтлично ❤️\n"
            "Теперь просто отправь свою фотографию 📸\n\nПромт писать не нужно."
        )
        return

    if not is_admin(update):
        return

    if data == "admin:channel":
        if not SESSIONS:
            await query.message.reply_text("Пока нет фотосессий.")
            return
        buttons = [[InlineKeyboardButton(s["title"], callback_data=f"channel_style:{k}")] for k, s in SESSIONS.items()]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="admin:home")])
        await query.message.reply_text("📢 Выбери фотосессию для поста:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("channel_style:"):
        key = data.split(":", 1)[1]
        if key not in SESSIONS:
            await query.message.reply_text("❌ Фотосессия не найдена.")
            return
        context.user_data["admin_state"] = "channel_caption"
        context.user_data["channel_style"] = key
        await query.message.reply_text(
            f"📢 Пост для:\n{SESSIONS[key]['title']}\n\nТеперь отправь текст поста."
        )
        return

    if data == "admin:home":
        context.user_data.clear()
        await query.message.reply_text("👑 Панель администратора\n\nВыбери действие:", reply_markup=admin_keyboard())
        return

    if data == "admin:add":
        context.user_data.clear()
        context.user_data["admin_state"] = "add_title"
        await query.message.reply_text("➕ Добавление фотосессии\n\nШаг 1 из 2.\n\nНапиши название новой фотосессии.\n\nНапример:\n🌊 Морская фотосессия")
        return

    if data == "admin:edit":
        if not SESSIONS:
            await query.message.reply_text("Пока нет фотосессий.")
            return
        buttons = [[InlineKeyboardButton(s["title"], callback_data=f"edit:{k}")] for k, s in SESSIONS.items()]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="admin:home")])
        await query.message.reply_text("✏️ Выбери фотосессию, промт которой нужно изменить:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data == "admin:delete":
        if not SESSIONS:
            await query.message.reply_text("Пока нет фотосессий.")
            return
        buttons = [[InlineKeyboardButton(f"🗑 {s['title']}", callback_data=f"delete:{k}")] for k, s in SESSIONS.items()]
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="admin:home")])
        await query.message.reply_text("🗑 Выбери фотосессию для удаления:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data == "admin:list":
        text = "📋 Фотосессий пока нет." if not SESSIONS else "📋 Твои фотосессии:\n\n" + "\n".join(f"{i}. {s['title']}" for i, s in enumerate(SESSIONS.values(), 1))
        await query.message.reply_text(text, reply_markup=admin_keyboard())
        return

    if data.startswith("edit:"):
        key = data.split(":", 1)[1]
        if key not in SESSIONS:
            await query.message.reply_text("❌ Фотосессия не найдена.")
            return
        context.user_data["admin_state"] = "edit_prompt"
        context.user_data["edit_key"] = key
        await query.message.reply_text(f"✏️ Изменяем:\n{SESSIONS[key]['title']}\n\nОтправь новый промт одним сообщением.")
        return

    if data.startswith("delete:"):
        key = data.split(":", 1)[1]
        if key not in SESSIONS:
            await query.message.reply_text("❌ Фотосессия не найдена.")
            return
        title = SESSIONS[key]["title"]
        del SESSIONS[key]
        save_sessions(SESSIONS)
        await query.message.reply_text(f"🗑 Удалено:\n{title}", reply_markup=admin_keyboard())

async def admin_text_handler(update, context):
    if not is_admin(update) or not update.message or not update.message.text:
        return
    state = context.user_data.get("admin_state")
    if not state:
        return
    text = update.message.text.strip()

    if state == "channel_caption":
        context.user_data["channel_caption"] = text
        context.user_data["admin_state"] = "channel_photo"
        await update.message.reply_text("📸 Теперь отправь фото для поста.")
        return

    if state == "add_title":
        context.user_data["new_title"] = text
        context.user_data["admin_state"] = "add_prompt"
        await update.message.reply_text("✅ Название сохранено.\n\nШаг 2 из 2.\n\nТеперь отправь промт для этой фотосессии.")
        return

    if state == "add_prompt":
        title = context.user_data.get("new_title")
        number = 1
        while f"custom_{number}" in SESSIONS:
            number += 1
        key = f"custom_{number}"
        SESSIONS[key] = {"title": title, "prompt": text}
        save_sessions(SESSIONS)
        context.user_data.clear()
        await update.message.reply_text(f"✅ Новая фотосессия создана!\n\n{title}\n\nТеперь она появилась в меню клиентов.", reply_markup=admin_keyboard())
        return

    if state == "edit_prompt":
        key = context.user_data.get("edit_key")
        if not key or key not in SESSIONS:
            context.user_data.clear()
            await update.message.reply_text("❌ Не удалось найти фотосессию.", reply_markup=admin_keyboard())
            return
        SESSIONS[key]["prompt"] = text
        save_sessions(SESSIONS)
        title = SESSIONS[key]["title"]
        context.user_data.clear()
        await update.message.reply_text(f"✅ Промт обновлён!\n\n{title}", reply_markup=admin_keyboard())

async def photo_handler(update, context):
    if not update.message:
        return

    if is_admin(update) and context.user_data.get("admin_state") == "channel_photo":
        key = context.user_data.get("channel_style")
        caption = context.user_data.get("channel_caption", "")
        if not key or key not in SESSIONS:
            context.user_data.clear()
            await update.message.reply_text("❌ Не удалось найти фотосессию.", reply_markup=admin_keyboard())
            return
        button = InlineKeyboardMarkup([[InlineKeyboardButton("📸 СДЕЛАТЬ ФОТО", url=f"https://t.me/{BOT_USERNAME}?start={key}")]])
        try:
            await context.bot.send_photo(chat_id=CHANNEL_USERNAME, photo=update.message.photo[-1].file_id, caption=caption, reply_markup=button)
            context.user_data.clear()
            await update.message.reply_text("✅ Пост опубликован в канал.", reply_markup=admin_keyboard())
        except Exception:
            logger.exception("Channel post error")
            await update.message.reply_text("❌ Не удалось опубликовать пост.\n\nПроверь, что бот добавлен в канал и имеет права администратора.")
        return

    style = context.user_data.get("selected_style")
    if not style:
        await update.message.reply_text("Сначала выбери фотосессию 👇", reply_markup=client_keyboard())
        return
    if style not in SESSIONS:
        await update.message.reply_text("❌ Эта фотосессия больше недоступна.", reply_markup=client_keyboard())
        return

    session = SESSIONS[style]
    await update.message.reply_text("📸 Фото получила!\n\n✨ Начинаю обработку...\nЭто может занять некоторое время.")

    try:
        telegram_file = await update.message.photo[-1].get_file()
        photo_bytes = await telegram_file.download_as_bytearray()
        image_file = io.BytesIO(bytes(photo_bytes))
        image_file.name = "photo.jpg"

        def generate_image():
            return client.images.edit(model="gpt-image-2", image=image_file, prompt=session["prompt"], size="1024x1536")

        result = await asyncio.to_thread(generate_image)
        if not result.data or not getattr(result.data[0], "b64_json", None):
            raise RuntimeError("OpenAI returned no image")
        generated_bytes = base64.b64decode(result.data[0].b64_json)
        output = io.BytesIO(generated_bytes)
        output.name = "ai_photo.png"
        await update.message.reply_photo(
            photo=output,
            caption=f"✨ Готово!\n\n{session['title']}\n\nХочешь ещё фото? Выбери другую фотосессию 👇",
            reply_markup=client_keyboard(),
        )
    except Exception:
        logger.exception("Image generation error")
        await update.message.reply_text("😔 Не удалось создать фотографию.\n\nПопробуй отправить фото ещё раз.")

async def unknown_text(update, context):
    if is_admin(update) and context.user_data.get("admin_state"):
        return
    await update.message.reply_text("Выбери фотосессию 👇", reply_markup=client_keyboard())

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("admin", admin_command))
telegram_app.add_handler(CallbackQueryHandler(callback_handler))
telegram_app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Telegram application...")
    await telegram_app.initialize()
    await telegram_app.start()
    render_url = os.environ.get("RENDER_EXTERNAL_URL") or "https://ai-photo-telegram-bot.onrender.com"
    webhook_url = render_url.rstrip("/") + "/telegram"
    await telegram_app.bot.set_webhook(webhook_url)
    logger.info("Webhook set: %s", webhook_url)
    logger.info("Telegram application started")
    yield
    logger.info("Stopping Telegram application...")
    try:
        await telegram_app.bot.delete_webhook()
    except Exception:
        logger.exception("Could not delete webhook")
    await telegram_app.stop()
    await telegram_app.shutdown()

app = FastAPI()


@app.get("/")
async def root():
    return {"status": "ok", "bot": "AI Photo Gallery"}


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
