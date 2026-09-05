import os
import io
import base64

from fastapi import FastAPI, Request
from openai import OpenAI
from prompts import get_session
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

import uvicorn


BOT_TOKEN = os.environ["BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI()

telegram_app = Application.builder().token(BOT_TOKEN).build()


# =========================
# ПРОМТЫ ФОТОСЕССИЙ
# =========================

PROMPTS = {

    "autumn": """
Create a luxurious photorealistic autumn fashion photoshoot.

Keep the person's identity exactly recognizable.
Preserve facial structure, eyes, nose, lips, eyebrows,
natural proportions and distinctive features.

Young woman in an elegant autumn fashion editorial
surrounded by beautiful red rowan berries and golden
autumn foliage.

Dynamic fashion editorial photography.
Natural movement and elegant posing.
Premium professional photography.
Realistic skin texture and natural pores.
Individual hair details.
Detailed fabric texture.
Beautiful natural autumn colors.
Soft cinematic daylight.
Physically realistic lighting and shadows.
Professional full-frame camera look.
Realistic depth of field.
Extremely detailed photorealistic image.

Do not change the person's identity.
Do not make the face look like another person.
Avoid plastic skin, beauty filters, excessive smoothing,
CGI appearance, artificial eyes or distorted features.
""",

    "luxury": """
Create a luxurious high-end professional fashion portrait.

Preserve the person's identity and recognizable facial features.
Keep the exact natural face shape and proportions.

Elegant luxury editorial styling.
Sophisticated premium atmosphere.
Expensive studio environment.
Professional fashion photography.
Natural realistic skin texture and pores.
Fine eyelashes and realistic eyes.
Detailed clothing and fabric texture.
Controlled cinematic studio lighting.
Beautiful highlights and natural shadows.
Full-frame professional camera look.
High dynamic range.
Realistic depth of field.
Extremely detailed photorealistic result.

No plastic skin.
No artificial beauty filter.
No excessive retouching.
No face alteration.
No CGI appearance.
""",

    "fashion": """
Create a professional high-fashion editorial photoshoot.

Preserve the person's identity exactly.
Do not change recognizable facial features or natural proportions.

Modern fashion magazine editorial.
Confident elegant pose.
Dynamic professional fashion photography.
Sophisticated styling and composition.
Natural realistic skin texture.
Visible fine skin details and pores.
Detailed clothing texture.
Professional studio and cinematic lighting.
Natural shadows.
Full-frame professional camera appearance.
High dynamic range.
Realistic depth of field.
Sharp fine details.
Photorealistic premium quality.

Do not change identity.
Avoid plastic skin, excessive smoothing,
beauty filters, distorted facial features or CGI.
""",

    "love": """
Create a romantic professional Love Story photoshoot.

Preserve the person's identity exactly and naturally.
Keep recognizable facial features and proportions.

Elegant romantic cinematic atmosphere.
Warm beautiful natural light.
Emotional sophisticated photography.
Natural body language and elegant posing.
Premium professional photography.
Realistic skin texture.
Natural pores and fine details.
Detailed clothing.
Physically accurate lighting and shadows.
Beautiful depth of field.
Full-frame professional camera look.
Photorealistic high-end result.

Do not change identity.
Avoid artificial beauty filters or plastic skin.
""",

    "romantic": """
Create a beautiful elegant romantic fashion portrait.

Preserve the person's identity and natural facial features.

Soft romantic atmosphere.
Elegant styling.
Delicate cinematic lighting.
Natural realistic skin texture.
Natural pores and fine details.
Professional editorial photography.
Beautiful composition.
Realistic shadows and highlights.
Full-frame camera look.
Natural depth of field.
Highly detailed photorealistic result.

Do not change the person's identity.
No artificial face changes.
No plastic skin or excessive smoothing.
""",

    "black": """
Create a dramatic black editorial fashion portrait.

Preserve the person's identity exactly.
Do not alter recognizable facial features or proportions.

Black luxury fashion editorial.
Dark sophisticated atmosphere.
Elegant powerful composition.
Dramatic professional studio lighting.
Deep realistic shadows.
Controlled highlights.
Natural skin texture and pores.
Detailed clothing and fabric.
Professional full-frame camera look.
High dynamic range.
Realistic depth of field.
Extremely detailed photorealistic result.

No plastic skin.
No beauty filter.
No face alteration.
No CGI appearance.
""",

    "children": """
Create a professional children's portrait photoshoot.

Preserve the child's identity exactly.
Keep natural facial features, proportions and recognizable appearance.

Beautiful natural child photography.
Warm elegant atmosphere.
Natural age-appropriate styling.
Authentic expression.
Professional portrait photography.
Soft natural lighting.
Realistic skin texture.
Natural pores and fine details.
Detailed clothing.
Beautiful realistic background.
Professional full-frame camera look.
Natural depth of field.
High-quality photorealistic result.

Do not make the child look older.
Do not change identity.
Do not use artificial beauty filters.
Avoid plastic skin and CGI appearance.
""",

    "men": """
Create a premium professional men's fashion portrait.

Preserve the person's identity exactly.
Keep facial structure, eyes, nose, lips,
eyebrows and natural proportions unchanged.

Confident masculine editorial style.
Modern luxury fashion photography.
Sophisticated professional atmosphere.
Natural realistic skin texture and pores.
Detailed clothing and fabric.
Professional studio or cinematic lighting.
Natural shadows.
Full-frame professional camera look.
High dynamic range.
Realistic depth of field.
Crisp fine details.
Photorealistic premium quality.

Do not change the person's identity.
Avoid plastic skin, excessive smoothing,
beauty filters, distorted facial features or CGI.
"""
}


# =========================
# МЕНЮ
# =========================

def main_menu():
    keyboard = [
        [
            InlineKeyboardButton("🍂 Осенняя", callback_data="autumn"),
            InlineKeyboardButton("💎 Luxury", callback_data="luxury"),
        ],
        [
            InlineKeyboardButton("👠 Fashion", callback_data="fashion"),
            InlineKeyboardButton("❤️ Love Story", callback_data="love"),
        ],
        [
            InlineKeyboardButton("🌸 Romantic", callback_data="romantic"),
            InlineKeyboardButton("🖤 Black Editorial", callback_data="black"),
        ],
        [
            InlineKeyboardButton("👶 Детская фотосессия", callback_data="children"),
        ],
        [
            InlineKeyboardButton("🤵 Мужская фотосессия", callback_data="men"),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["style"] = None

    await update.message.reply_text(
        "✨ Добро пожаловать в AI Photo Gallery!\n\n"
        "Выбери фотосессию 👇\n\n"
        "После выбора просто отправь фотографию 📸\n"
        "Промт писать не нужно — я всё сделаю сама ❤️",
        reply_markup=main_menu()
    )


# =========================
# НАЖАТИЕ КНОПКИ
# =========================

async def button_click(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    style = query.data

    context.user_data["style"] = style

    names = {
        "autumn": "🍂 Осенняя фотосессия",
        "luxury": "💎 Luxury",
        "fashion": "👠 Fashion",
        "love": "❤️ Love Story",
        "romantic": "🌸 Romantic",
        "black": "🖤 Black Editorial",
        "children": "👶 Детская фотосессия",
        "men": "🤵 Мужская фотосессия",
    }

    await query.message.reply_text(
        f"Выбрано: {names.get(style, 'Фотосессия')} ✨\n\n"
        "Теперь отправь фотографию 📸\n\n"
        "Лучше отправлять оригинальное фото "
        "как файл, чтобы сохранить максимум качества."
    )


# =========================
# ОБРАБОТКА ФОТО
# =========================

async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    style = context.user_data.get("style")

    if not style:
        await message.reply_text(
            "Сначала выбери фотосессию 👇",
            reply_markup=main_menu()
        )
        return

    await message.reply_text(
        "📸 Обрабатываю фотографию...\n\n"
        "Сохраняю лицо и улучшаю качество ✨\n"
        "Подожди немного ❤️"
    )

    try:

        if message.photo:

            photo = message.photo[-1]

            telegram_file = await photo.get_file()

        elif message.document and message.document.mime_type:

            telegram_file = await message.document.get_file()

        else:

            await message.reply_text(
                "Пожалуйста, отправь фотографию 📷"
            )

            return

        image_bytes = await telegram_file.download_as_bytearray()

        image_file = io.BytesIO(image_bytes)

        image_file.name = "input.jpg"

        prompt = PROMPTS[style]

        result = client.images.edit(
            model="gpt-image-2",
            image=image_file,
            prompt=prompt,
            size="1024x1536",
        )

        image_base64 = result.data[0].b64_json

        result_bytes = base64.b64decode(image_base64)

        output = io.BytesIO(result_bytes)

        output.name = "ai_photo.png"

        await message.reply_photo(
            photo=output,
            caption=(
                "✨ Готово!\n\n"
                "📸 Твоя профессиональная фотосессия."
            )
        )

        # Возвращаем меню для следующей фотографии

        await message.reply_text(
            "Хочешь сделать ещё одну? 👇",
            reply_markup=main_menu()
        )

    except Exception as error:

        print("ERROR:", error)

        await message.reply_text(
            "❌ Не удалось обработать фотографию.\n\n"
            "Попробуй отправить её ещё раз."
        )


# =========================
# TELEGRAM HANDLERS
# =========================

telegram_app.add_handler(
    CommandHandler("start", start)
)

telegram_app.add_handler(
    CallbackQueryHandler(button_click)
)

telegram_app.add_handler(
    MessageHandler(
        filters.PHOTO | filters.Document.IMAGE,
        handle_photo
    )
)


# =========================
# FASTAPI
# =========================

@app.get("/")
async def home():

    return {
        "status": "AI Photo Gallery bot is running"
    }


@app.post("/telegram")
async def telegram_webhook(
    request: Request
):

    data = await request.json()

    update = Update.de_json(
        data=data,
        bot=telegram_app.bot
    )

    await telegram_app.process_update(update)

    return {"ok": True}


# =========================
# STARTUP
# =========================

@app.on_event("startup")
async def startup():

    await telegram_app.initialize()

    await telegram_app.start()

    render_url = os.environ.get(
        "RENDER_EXTERNAL_URL",
        ""
    ).rstrip("/")

    if render_url:

        webhook_url = (
            f"{render_url}/telegram"
        )

        await telegram_app.bot.set_webhook(
            webhook_url
        )

        print(
            "Webhook set:",
            webhook_url
        )


# =========================
# SHUTDOWN
# =========================

@app.on_event("shutdown")
async def shutdown():

    await telegram_app.stop()

    await telegram_app.shutdown()


# =========================
# RUN
# =========================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
    )
