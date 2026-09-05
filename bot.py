import os
import io
import json
import base64
import asyncio
import logging

from fastapi import FastAPI, Request
from openai import OpenAI

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================================================
# НАСТРОЙКИ
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY не найден")


client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI()

telegram_app = Application.builder().token(BOT_TOKEN).build()

PROMPTS_FILE = "prompts.json"


# =========================================================
# ГОТОВЫЕ ФОТОСЕССИИ
# =========================================================

DEFAULT_SESSIONS = {
    "autumn": {
        "title": "🍂 Осенняя",
        "prompt": """
Create a photorealistic premium autumn fashion editorial photograph.

IMPORTANT:
Preserve the person's identity from the uploaded reference photo.
Do not change facial structure, facial proportions, eyes, nose, lips,
eyebrows, skin tone, age or recognizable appearance.

Create a beautiful young woman in an elegant autumn fashion look
surrounded by natural branches of red rowan berries and golden autumn
foliage.

The composition should feel dynamic and alive, like a professional
fashion editorial action photograph rather than a static portrait.

Warm natural autumn atmosphere, rich red rowan berries, golden leaves,
soft elegant clothing, realistic fabric texture.

Professional full-frame camera photography, realistic skin texture,
visible natural pores, detailed eyelashes and hair, physically accurate
lighting, realistic shadows, cinematic depth of field, crisp details,
HDR-quality image.

No plastic skin, no beauty filter, no artificial face smoothing,
no CGI appearance, no distorted anatomy, no extra fingers.
"""
    },

    "luxury": {
        "title": "💎 Luxury",
        "prompt": """
Create a photorealistic luxury fashion editorial portrait.

Preserve the person's identity from the uploaded reference photo exactly.
Do not alter facial structure, facial proportions, eyes, nose, lips,
eyebrows, skin tone, age or recognizable appearance.

Create an expensive sophisticated editorial atmosphere with elegant
luxury styling, premium textures, refined fashion, subtle jewelry and
an upscale cinematic environment.

Soft dramatic studio lighting, controlled highlights and shadows,
natural skin texture, realistic pores, detailed eyelashes, realistic
hair and fabric.

Professional full-frame fashion photography, shallow depth of field,
high dynamic range, physically accurate light, extremely realistic
details.

Avoid plastic skin, excessive retouching, beauty filters, CGI,
artificial smoothing or distorted anatomy.
"""
    },

    "fashion": {
        "title": "👠 Fashion",
        "prompt": """
Create a high-end professional fashion editorial photograph.

Preserve the person's identity from the uploaded reference image.
Do not change facial structure, proportions, eyes, nose, lips,
eyebrows, skin tone, age or recognizable appearance.

Create a confident modern fashion pose with sophisticated designer-style
clothing and a premium editorial environment.

The photograph should feel dynamic, stylish and contemporary,
like a professional fashion campaign.

Professional full-frame camera look, realistic skin pores,
natural skin texture, detailed eyelashes, realistic hair and fabric,
cinematic lighting, accurate shadows, realistic depth of field,
high dynamic range and crisp details.

No plastic skin, no beauty filter, no face reshaping, no CGI,
no artificial smoothing and no distorted anatomy.
"""
    },

    "love": {
        "title": "❤️ Love Story",
        "prompt": """
Create a romantic photorealistic cinematic love-story photograph.

Preserve the identity of the person from the uploaded reference photo.
Do not alter facial structure, facial proportions, eyes, nose, lips,
eyebrows, skin tone, age or recognizable appearance.

Create an emotional romantic scene with natural body language,
warm atmosphere and authentic intimacy.

Use beautiful cinematic evening light, soft highlights, realistic
shadows and natural depth of field.

Professional full-frame photography, realistic skin texture,
natural pores, realistic eyelashes and hair, detailed clothing texture,
physically accurate lighting and realistic colors.

The result must look like a real professional photography session,
not an AI illustration.

No plastic skin, no beauty filter, no excessive smoothing,
no CGI appearance or distorted anatomy.
"""
    },

    "romantic": {
        "title": "🌸 Romantic",
        "prompt": """
Create a delicate photorealistic romantic fashion editorial portrait.

Preserve the person's exact recognizable identity from the reference.
Do not change facial structure, proportions, eyes, nose, lips,
eyebrows, skin tone, age or recognizable appearance.

Create an elegant feminine atmosphere with soft romantic styling,
beautiful surroundings and natural graceful posing.

Soft diffused cinematic lighting, delicate highlights,
natural shadows and realistic depth of field.

Professional full-frame camera photography, natural skin texture,
realistic pores, eyelashes, hair and fabric details.

The photograph must look authentic and professionally photographed.

No plastic skin, beauty filter, artificial smoothing,
CGI appearance or distorted anatomy.
"""
    },

    "black": {
        "title": "🖤 Black Editorial",
        "prompt": """
Create a dramatic high-fashion black editorial photograph.

Preserve the person's identity from the uploaded reference photo.
Do not alter facial structure, proportions, eyes, nose, lips,
eyebrows, skin tone, age or recognizable appearance.

Create a powerful sophisticated fashion editorial using a dark,
minimal premium environment and elegant black styling.

Strong cinematic directional lighting, deep realistic shadows,
controlled highlights and sophisticated contrast.

Professional full-frame fashion photography, realistic skin pores,
natural skin texture, detailed eyelashes, realistic hair and fabric,
physically accurate light, realistic depth of field and crisp detail.

Luxury magazine editorial feeling.

No plastic skin, no beauty filter, no excessive retouching,
no CGI, no face distortion and no artificial smoothing.
"""
    },

    "child": {
        "title": "👶 Детская фотосессия",
        "prompt": """
Create a beautiful photorealistic professional children's portrait.

Preserve the child's recognizable identity from the uploaded reference
photo. Do not change facial structure, facial proportions, eyes, nose,
lips, eyebrows, skin tone, age or recognizable appearance.

Create a warm professional children's fashion photoshoot with a natural,
age-appropriate atmosphere.

Beautiful soft natural lighting, realistic skin texture,
natural expressions, realistic clothing and environment.

Professional full-frame camera photography, realistic depth of field,
physically accurate shadows and highlights, high dynamic range,
crisp natural details.

The result must look like a real professional photograph.

No adult appearance, no excessive makeup, no plastic skin,
no beauty filter, no CGI, no artificial smoothing and no distorted anatomy.
"""
    },

    "man": {
        "title": "🤵 Мужская фотосессия",
        "prompt": """
Create a photorealistic premium men's fashion editorial portrait.

Preserve the person's exact recognizable identity from the uploaded
reference photo.

Do not change facial structure, facial proportions, eyes, nose, lips,
eyebrows, skin tone, age or recognizable appearance.

Create a confident sophisticated masculine fashion portrait with
premium clothing and cinematic editorial styling.

Professional full-frame camera photography, realistic skin pores,
natural skin texture, realistic hair and clothing texture,
physically accurate lighting, realistic shadows and highlights,
cinematic depth of field and crisp details.

The result should look like a real professional fashion photograph.

No plastic skin, no beauty filter, no artificial smoothing,
no CGI appearance and no distorted anatomy.
"""
    },
}


# =========================================================
# РАБОТА С ФОТОСЕССИЯМИ
# =========================================================

def load_sessions():
    if not os.path.exists(PROMPTS_FILE):
        return DEFAULT_SESSIONS.copy()

    try:
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict) and data:
            return data

    except Exception:
        logging.exception("Ошибка чтения prompts.json")

    return DEFAULT_SESSIONS.copy()


def save_sessions(sessions):
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(
            sessions,
            f,
            ensure_ascii=False,
            indent=2
        )


SESSIONS = load_sessions()


# =========================================================
# ПРОВЕРКА АДМИНА
# =========================================================

def is_admin(user_id):
    if not ADMIN_ID:
        return False

    try:
        return int(user_id) == int(ADMIN_ID)
    except Exception:
        return False


# =========================================================
# КЛИЕНТСКОЕ МЕНЮ
# =========================================================

def client_keyboard():
    buttons = []

    for session_id, session in SESSIONS.items():
        buttons.append(
            InlineKeyboardButton(
                session["title"],
                callback_data=f"style:{session_id}"
            )
        )

    keyboard = []

    for i in range(0, len(buttons), 2):
        keyboard.append(buttons[i:i + 2])

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# АДМИНСКОЕ МЕНЮ
# =========================================================

def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Добавить фотосессию",
                callback_data="admin:add"
            )
        ],
        [
            InlineKeyboardButton(
                "✏️ Изменить промт",
                callback_data="admin:edit"
            )
        ],
        [
            InlineKeyboardButton(
                "🗑 Удалить фотосессию",
                callback_data="admin:delete"
            )
        ],
        [
            InlineKeyboardButton(
                "📋 Мои фотосессии",
                callback_data="admin:list"
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Главное меню",
                callback_data="admin:home"
            )
        ],
    ])


# =========================================================
# /START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await update.message.reply_text(
        "✨ Добро пожаловать в AI Photo Gallery!\n\n"
        "Выбери фотосессию 👇\n\n"
        "После выбора просто отправь фотографию 📸\n"
        "Промт писать не нужно — я всё сделаю сама ❤️",
        reply_markup=client_keyboard()
    )


# =========================================================
# /ADMIN
# =========================================================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text(
            "⛔ У тебя нет доступа к панели администратора."
        )
        return

    context.user_data.clear()

    await update.message.reply_text(
        "👑 Панель администратора\n\n"
        "Здесь ты можешь управлять фотосессиями и промтами.",
        reply_markup=admin_keyboard()
    )


# =========================================================
# CALLBACK-КНОПКИ
# =========================================================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    data = query.data
    user_id = query.from_user.id

    # -----------------------------------------------------
    # КЛИЕНТ ВЫБРАЛ ФОТОСЕССИЮ
    # -----------------------------------------------------

    if data.startswith("style:"):
        style_id = data.split(":", 1)[1]

        if style_id not in SESSIONS:
            await query.message.reply_text(
                "❌ Эта фотосессия больше недоступна."
            )
            return

        context.user_data["selected_style"] = style_id

        session_title = SESSIONS[style_id]["title"]

        await query.message.reply_text(
            f"✨ Ты выбрала: {session_title}\n\n"
            "Теперь просто отправь фотографию 📸\n"
            "Промт писать не нужно ❤️"
        )

        return

    # -----------------------------------------------------
    # ПРОВЕРКА АДМИНА
    # -----------------------------------------------------

    if not is_admin(user_id):
        await query.message.reply_text(
            "⛔ Доступ запрещён."
        )
        return

    # -----------------------------------------------------
    # АДМИН: ДОБАВИТЬ
    # -----------------------------------------------------

    if data == "admin:add":
        context.user_data["admin_action"] = "add_title"

        await query.message.reply_text(
            "➕ Добавление фотосессии\n\n"
            "Напиши название новой фотосессии.\n\n"
            "Например:\n"
            "🌹 Красная роза"
        )

        return

    # -----------------------------------------------------
    # АДМИН: ИЗМЕНИТЬ
    # -----------------------------------------------------

    if data == "admin:edit":
        if not SESSIONS:
            await query.message.reply_text(
                "Нет доступных фотосессий."
            )
            return

        keyboard = []

        for session_id, session in SESSIONS.items():
            keyboard.append([
                InlineKeyboardButton(
                    session["title"],
                    callback_data=f"edit:{session_id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "⬅️ Назад",
                callback_data="admin:back"
            )
        ])

        await query.message.reply_text(
            "✏️ Выбери фотосессию, промт которой нужно изменить:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return

    # -----------------------------------------------------
    # АДМИН: ВЫБОР ДЛЯ ИЗМЕНЕНИЯ
    # -----------------------------------------------------

    if data.startswith("edit:"):
        style_id = data.split(":", 1)[1]

        if style_id not in SESSIONS:
            await query.message.reply_text(
                "❌ Фотосессия не найдена."
            )
            return

        context.user_data["admin_action"] = "edit_prompt"
        context.user_data["edit_style"] = style_id

        await query.message.reply_text(
            f"✏️ Изменение промта\n\n"
            f"Фотосессия: {SESSIONS[style_id]['title']}\n\n"
            "Теперь отправь новый промт одним сообщением."
        )

        return

    # -----------------------------------------------------
    # АДМИН: УДАЛЕНИЕ
    # -----------------------------------------------------

    if data == "admin:delete":
        keyboard = []

        for session_id, session in SESSIONS.items():
            keyboard.append([
                InlineKeyboardButton(
                    session["title"],
                    callback_data=f"delete:{session_id}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "⬅️ Назад",
                callback_data="admin:back"
            )
        ])

        await query.message.reply_text(
            "🗑 Выбери фотосессию для удаления:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return

    # -----------------------------------------------------
    # ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ
    # -----------------------------------------------------

    if data.startswith("delete:"):
        style_id = data.split(":", 1)[1]

        if style_id not in SESSIONS:
            await query.message.reply_text(
                "❌ Фотосессия уже удалена."
            )
            return

        title = SESSIONS[style_id]["title"]

        del SESSIONS[style_id]
        save_sessions(SESSIONS)

        await query.message.reply_text(
            f"🗑 Фотосессия «{title}» удалена.",
            reply_markup=admin_keyboard()
        )

        return

    # -----------------------------------------------------
    # СПИСОК ФОТОСЕССИЙ
    # -----------------------------------------------------

    if data == "admin:list":
        if not SESSIONS:
            text = "📋 Фотосессий пока нет."
        else:
            lines = ["📋 Твои фотосессии:\n"]

            for number, session in enumerate(
                SESSIONS.values(),
                start=1
            ):
                lines.append(
                    f"{number}. {session['title']}"
                )

            text = "\n".join(lines)

        await query.message.reply_text(
            text,
            reply_markup=admin_keyboard()
        )

        return

    # -----------------------------------------------------
    # НАЗАД
    # -----------------------------------------------------

    if data in ("admin:back", "admin:home"):
        context.user_data.clear()

        await query.message.reply_text(
            "👑 Панель администратора",
            reply_markup=admin_keyboard()
        )

        return


# =========================================================
# ТЕКСТ ОТ АДМИНА
# =========================================================

async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        return

    action = context.user_data.get("admin_action")
    text = update.message.text.strip()

    # -----------------------------------------------------
    # НОВОЕ НАЗВАНИЕ
    # -----------------------------------------------------

    if action == "add_title":
        context.user_data["new_title"] = text
        context.user_data["admin_action"] = "add_prompt"

        await update.message.reply_text(
            "✅ Название сохранено.\n\n"
            "Теперь отправь промт для этой фотосессии "
            "одним сообщением."
        )

        return

    # -----------------------------------------------------
    # НОВЫЙ ПРОМТ
    # -----------------------------------------------------

    if action == "add_prompt":
        title = context.user_data.get("new_title")

        new_id = f"custom_{len(SESSIONS) + 1}"

        while new_id in SESSIONS:
            new_id = f"custom_{len(SESSIONS) + 2}"

        SESSIONS[new_id] = {
            "title": title,
            "prompt": text
        }

        save_sessions(SESSIONS)

        context.user_data.clear()

        await update.message.reply_text(
            "🎉 Готово!\n\n"
            f"Новая фотосессия: {title}\n"
            "Добавлена в меню клиентов.",
            reply_markup=admin_keyboard()
        )

        return

    # -----------------------------------------------------
    # ИЗМЕНЕНИЕ ПРОМТА
    # -----------------------------------------------------

    if action == "edit_prompt":
        style_id = context.user_data.get("edit_style")

        if style_id not in SESSIONS:
            context.user_data.clear()

            await update.message.reply_text(
                "❌ Фотосессия не найдена."
            )
            return

        SESSIONS[style_id]["prompt"] = text

        save_sessions(SESSIONS)

        title = SESSIONS[style_id]["title"]

        context.user_data.clear()

        await update.message.reply_text(
            f"✅ Промт фотосессии «{title}» успешно изменён.",
            reply_markup=admin_keyboard()
        )

        return


# =========================================================
# ОБРАБОТКА ФОТО
# =========================================================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    style_id = context.user_data.get("selected_style")

    if not style_id:
        await update.message.reply_text(
            "Сначала выбери фотосессию 👇",
            reply_markup=client_keyboard()
        )
        return

    if style_id not in SESSIONS:
        await update.message.reply_text(
            "❌ Эта фотосессия больше недоступна."
        )
        return

    prompt = SESSIONS[style_id]["prompt"]

    await update.message.reply_text(
        "⏳ Обрабатываю фотографию...\n\n"
        "Это может занять немного времени ❤️"
    )

    try:
        photo = update.message.photo[-1]

        telegram_file = await context.bot.get_file(
            photo.file_id
        )

        image_bytes = await telegram_file.download_as_bytearray()

        image_file = io.BytesIO(bytes(image_bytes))
        image_file.name = "input.jpg"

        # OpenAI вызов выполняем в отдельном потоке,
        # чтобы бот не зависал во время генерации.
        result = await asyncio.to_thread(
            client.images.edit,
            model="gpt-image-2",
            image=image_file,
            prompt=prompt,
            size="1024x1536",
        )

        if not result.data:
            raise RuntimeError("OpenAI не вернул изображение")

        image_data = result.data[0].b64_json

        if not image_data:
            raise RuntimeError("В ответе нет изображения")

        output_bytes = base64.b64decode(image_data)

        output_file = io.BytesIO(output_bytes)
        output_file.name = "ai_photo.png"

        await update.message.reply_photo(
            photo=output_file,
            caption="✨ Готово!\n\n"
                    "Если хочешь попробовать другой образ — "
                    "выбери новую фотосессию 👇",
            reply_markup=client_keyboard()
        )

    except Exception as e:
        logging.exception("Ошибка генерации")

        await update.message.reply_text(
            "😔 Не получилось создать фотографию.\n\n"
            "Попробуй отправить фото ещё раз."
        )


# =========================================================
# WEBHOOK
# =========================================================

@app.get("/")
async def health():
    return {
        "status": "ok",
        "bot": "AI Photo Gallery"
    }


@app.post("/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()

    update = Update.de_json(
        data,
        telegram_app.bot
    )

    await telegram_app.process_update(update)

    return {"ok": True}


# =========================================================
# ЗАПУСК
# =========================================================

async def startup():
    await telegram_app.initialize()
    await telegram_app.start()

    webhook_url = (
        "https://ai-photo-telegram-bot.onrender.com/telegram"
    )

    await telegram_app.bot.set_webhook(
        url=webhook_url,
        drop_pending_updates=True
    )

    logging.info(
        f"Webhook установлен: {webhook_url}"
    )


async def shutdown():
    await telegram_app.bot.delete_webhook()

    await telegram_app.stop()
    await telegram_app.shutdown()


app.add_event_handler(
    "startup",
    startup
)

app.add_event_handler(
    "shutdown",
    shutdown
)


# =========================================================
# HANDLERS
# =========================================================

telegram_app.add_handler(
    CommandHandler("start", start)
)

telegram_app.add_handler(
    CommandHandler("admin", admin_command)
)

telegram_app.add_handler(
    CallbackQueryHandler(callbacks)
)

telegram_app.add_handler(
    MessageHandler(
        filters.PHOTO,
        handle_photo
    )
)

telegram_app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_text
    )
)


# =========================================================
# ЛОГИ
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


# =========================================================
# UVICORN
# =========================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 10000))

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
    )
