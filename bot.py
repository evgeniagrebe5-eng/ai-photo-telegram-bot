import os
import io
import base64

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


BOT_TOKEN = os.environ["BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI()

telegram_app = Application.builder().token(BOT_TOKEN).build()


QUALITY_PROMPT = """
Create a highly realistic professional photograph from the uploaded image.

Preserve the person's identity and recognizable facial features as accurately as possible.
Do not change the face shape, eyes, nose, lips, eyebrows, or natural proportions.

Improve photographic quality while keeping the person natural and realistic.

Professional full-frame camera look.
Extremely detailed realistic skin texture.
Natural pores.
Fine eyelashes.
Individual hair details.
Realistic fabric texture.
Physically accurate lighting.
Natural shadows.
High dynamic range.
Realistic depth of field.
Crisp fine details.
Premium professional photography.
Photorealistic result.

Do not make the person look like another person.

Avoid plastic skin, artificial beauty filters, excessive smoothing,
over-sharpening, distorted facial features, unrealistic eyes,
or an artificial CGI appearance.
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 📸\n\n"
        "Отправь мне свою фотографию, и я создам "
        "улучшенную профессиональную версию.\n\n"
        "✨ Сохраняю лицо\n"
        "✨ Улучшаю качество\n"
        "✨ Повышаю детализацию\n"
        "✨ Делаю фотографию более профессиональной"
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    await message.reply_text(
        "📸 Обрабатываю фотографию...\n"
        "Немного подожди ❤️"
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

        result = client.images.edit(
            model="gpt-image-2",
            image=image_file,
            prompt=QUALITY_PROMPT,
            size="1024x1536",
        )

        image_base64 = result.data[0].b64_json
        result_bytes = base64.b64decode(image_base64)

        await message.reply_photo(
            photo=io.BytesIO(result_bytes),
            caption="✨ Готово! Профессиональная версия фотографии."
        )

    except Exception as error:
        print("ERROR:", error)

        await message.reply_text(
            "❌ Не удалось обработать фотографию.\n"
            "Попробуй отправить её ещё раз."
        )


telegram_app.add_handler(
    CommandHandler("start", start)
)

telegram_app.add_handler(
    MessageHandler(
        filters.PHOTO | filters.Document.IMAGE,
        handle_photo
    )
)


@app.get("/")
async def home():
    return {"status": "AI Photo Gallery bot is running"}


@app.post("/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()

    update = Update.de_json(
        data=data,
        bot=telegram_app.bot
    )

    await telegram_app.process_update(update)

    return {"ok": True}


@app.on_event("startup")
async def startup():
    await telegram_app.initialize()
    await telegram_app.start()

    render_url = os.environ.get(
        "RENDER_EXTERNAL_URL",
        ""
    ).rstrip("/")

    if render_url:
        webhook_url = f"{render_url}/telegram"

        await telegram_app.bot.set_webhook(
            webhook_url
        )

        print(
            "Webhook set:",
            webhook_url
        )


@app.on_event("shutdown")
async def shutdown():
    await telegram_app.stop()
    await telegram_app.shutdown()


if __name__ == "__main__":
    port = int(
        os.environ.get("PORT", "10000")
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
    )
