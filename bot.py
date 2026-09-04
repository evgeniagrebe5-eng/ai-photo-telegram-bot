import os
import io
import base64
import asyncio

from fastapi import FastAPI, Request
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import uvicorn


# =========================
# НАСТРОЙКИ
# =========================

BOT_TOKEN = os.environ["BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

WEBHOOK_URL = os.environ.get(
    "WEBHOOK_URL",
    os.environ.get("RENDER_EXTERNAL_URL", "")
).rstrip("/")

PORT = int(os.environ.get("PORT", "10000"))


# =========================
# OPENAI
# =========================

openai_client = OpenAI(api_key=OPENAI_API_KEY)


# =========================
# TELEGRAM
# =========================

telegram_app = Application.builder().token(BOT_TOKEN).build()


# =========================
# FASTAPI
# =========================

app = FastAPI()


# =========================
# ПРОМТ КАЧЕСТВА
# =========================

QUALITY_PROMPT = """
Create a highly realistic professional photograph from the uploaded image.

Preserve the person's identity and recognizable facial features as accurately
as possible. Do not change the face shape, eyes, nose, lips, eyebrows,
or natural proportions.

Improve photographic quality while keeping the person natural and realistic.

Professional full-frame camera look, extremely detailed realistic skin
texture, natural pores, fine eyelashes, individual hair details,
realistic fabric texture, physically accurate lighting, natural shadows,
high dynamic range, realistic depth of field, crisp fine details,
premium professional photography, photorealistic result.

Avoid plastic skin, artificial beauty filters, excessive smoothing,
over-sharpening, distorted facial features, unrealistic eyes,
or an artificial CGI appearance.
"""


# =========================
# /start
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 📸\n\n"
        "Отправь мне свою фотографию, и я создам "
        "улучшенную профессиональную версию.\n\n"
        "✨ Сохраняю лицо\n"
        "✨ Улучшаю детализацию\n"
        "✨ Делаю фотографию более профессиональной"
    )


# =========================
# ОБРАБОТКА ФОТО
# =========================

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):

    message = update.message

    try:
        await message.reply_text(
            "⏳ Обрабатываю фотографию...\n\n"
            "Это может занять немного времени."
        )

        # Если пользователь отправил обычное фото
        if message.photo:
            telegram_photo = message.photo[-1]
            telegram_file = await telegram_photo.get_file()

        # Если пользователь отправил фото как файл
        elif message.document and message.document.mime_type:
            telegram_file = await message.document.get_file()

        else:
            return

        # Загружаем изображение из Telegram
        image_bytes = await telegram_file.download_as_bytearray()

        image_file = io.BytesIO(image_bytes)
        image_file.name = "photo.jpg"

        # Запускаем OpenAI
        result = await asyncio.to_thread(
            openai_client.images.edit,
            model="gpt-image-2",
            image=image_file,
            prompt=QUALITY_PROMPT,
            size="1024x1536",
        )

        # Получаем готовое изображение
        image_base64 = result.data[0].b64_json
        output_bytes = base64.b64decode(image_base64)

        output_file = io.BytesIO(output_bytes)
        output_file.name = "ai_photo.png"

        # Отправляем результат
        await message.reply_photo(
            photo=output_file,
            caption="✨ Готово!\n\n"
                    "Твоя фотография обработана с помощью GPT-Image-2."
        )

    except Exception as error:

        print("ERROR:", error)

        await message.reply_text(
            "❌ Не получилось обработать фотографию.\n\n"
            "Попробуй отправить другое фото."
        )


# =========================
# HANDLERS
# =========================

telegram_app.add_handler(
    CommandHandler("start", start)
)

telegram_app.add_handler(
    MessageHandler(filters.PHOTO, handle_image)
)

telegram_app.add_handler(
    MessageHandler(filters.Document.IMAGE, handle_image)
)


# =========================
# WEBHOOK
# =========================

@app.on_event("startup")
async def startup():

    await telegram_app.initialize()
    await telegram_app.start()

    if WEBHOOK_URL:
        await telegram_app.bot.set_webhook(
            url=f"{WEBHOOK_URL}/telegram"
        )

        print("Webhook установлен:", WEBHOOK_URL)


@app.on_event("shutdown")
async def shutdown():

    await telegram_app.stop()
    await telegram_app.shutdown()


@app.get("/")
async def home():

    return {
        "status": "ok",
        "bot": "AI Photo Telegram Bot"
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


# =========================
# ЗАПУСК
# =========================

if __name__ == "__main__":

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT
    )
