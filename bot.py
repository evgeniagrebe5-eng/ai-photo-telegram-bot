import os
import io
import json
import base64

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
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import uvicorn


# ==========================================
# НАСТРОЙКИ
# ==========================================

BOT_TOKEN = os.environ["BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

ADMIN_ID = 7003476980

client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI()

telegram_app = (
    Application.builder()
    .token(BOT_TOKEN)
    .build()
)

PROMPTS_FILE = "prompts.json"


# ==========================================
# ГОТОВЫЕ ПРОМТЫ
# ==========================================

DEFAULT_PROMPTS = {

    "autumn": {
        "name": "🍂 Осенняя",
        "prompt": """
Create a premium photorealistic autumn fashion editorial photograph.

Create an elegant autumn photoshoot with warm golden foliage,
natural red rowan berries, beautiful autumn atmosphere,
cinematic natural light and sophisticated fashion styling.

Professional full-frame camera look.
Extremely realistic skin texture.
Natural pores.
Fine eyelashes.
Individual hair details.
Realistic fabric texture.
Natural shadows.
High dynamic range.
Realistic depth of field.
Crisp fine details.

Preserve the person's identity and recognizable facial features
as accurately as possible.

Do not change the face shape, eyes, nose, lips, eyebrows,
or natural facial proportions.

The result must look like a real professional photograph.

Avoid plastic skin, beauty filters, excessive smoothing,
over-sharpening, distorted facial features, unrealistic eyes,
or CGI appearance.
"""
    },

    "luxury": {
        "name": "💎 Luxury",
        "prompt": """
Create a luxurious high-end fashion editorial photograph.

Sophisticated premium atmosphere, elegant styling,
cinematic professional lighting, refined composition,
luxury fashion magazine aesthetic.

Professional full-frame camera look.
Realistic skin texture.
Natural pores.
Detailed eyelashes.
Individual hair details.
Realistic fabric texture.
Physically accurate lighting.
Natural shadows.
High dynamic range.
Realistic depth of field.

Preserve the person's identity and recognizable facial features
as accurately as possible.

Do not change the face shape, eyes, nose, lips, eyebrows,
or natural facial proportions.

Photorealistic premium photography.

No plastic skin, no artificial beauty filter,
no CGI appearance.
"""
    },

    "fashion": {
        "name": "👠 Fashion",
        "prompt": """
Create a professional high-fashion editorial photograph.

Dynamic sophisticated fashion pose.
Premium fashion magazine aesthetic.
Elegant composition.
Professional cinematic lighting.
Natural realistic environment.

Professional full-frame camera look.
Highly detailed realistic skin texture.
Natural pores.
Fine eyelashes.
Individual hair details.
Detailed clothing texture.
Natural shadows.
High dynamic range.
Realistic depth of field.

Preserve the person's identity and recognizable facial features
as accurately as possible.

Do not change facial proportions or make the person
look like another person.

Photorealistic professional fashion photography.

No plastic skin.
No artificial beauty filter.
No CGI.
"""
    },

    "love": {
        "name": "❤️ Love Story",
        "prompt": """
Create an emotional romantic professional editorial photograph.

Warm intimate atmosphere.
Beautiful cinematic lighting.
Elegant composition.
Natural realistic colors.
Premium photography aesthetic.

Professional full-frame camera look.
Realistic skin texture.
Natural pores.
Detailed clothing.
Physically accurate lighting.
Realistic depth of field.

Preserve the person's identity and recognizable facial features
as accurately as possible.

Do not change the face shape, eyes, nose, lips,
eyebrows or natural proportions.

Photorealistic professional photography.

No artificial beauty filter.
No plastic skin.
No CGI appearance.
"""
    },

    "romantic": {
        "name": "🌸 Romantic",
        "prompt": """
Create a beautiful romantic fashion editorial photograph.

Soft elegant atmosphere.
Delicate cinematic light.
Sophisticated styling.
Natural warm tones.
Beautiful realistic background.
Premium magazine photography.

Extremely realistic skin texture.
Natural pores.
Detailed eyelashes.
Realistic fabric.
Physically accurate lighting.
Professional full-frame camera look.
Realistic depth of field.

Preserve the person's identity and recognizable facial features
as accurately as possible.

Do not change facial proportions.

Photorealistic result.

No plastic skin.
No excessive retouching.
No CGI.
"""
    },

    "black": {
        "name": "🖤 Black Editorial",
        "prompt": """
Create a dramatic black fashion editorial photograph.

Elegant dark styling.
Sophisticated black atmosphere.
Cinematic studio lighting.
Deep realistic shadows.
Premium fashion magazine aesthetic.
Dramatic professional composition.

Extremely detailed realistic skin texture.
Natural pores.
Individual hair details.
Realistic fabric texture.
Physically accurate lighting.
High dynamic range.
Realistic depth of field.

Professional full-frame camera look.

Preserve the person's identity and recognizable facial features
as accurately as possible.

Do not change facial proportions or make the person
look like someone else.

Photorealistic professional photography.

No plastic skin.
No artificial beauty filter.
No CGI.
"""
    },

    "child": {
        "name": "👶 Детская",
        "prompt": """
Create a beautiful professional children's portrait photograph.

Natural child photography with a warm, joyful and authentic
atmosphere.

Soft professional lighting.
Natural colors.
Realistic skin texture.
Natural childlike facial proportions.
Detailed clothing texture.
Realistic eyes.
Natural expression.
Professional full-frame camera look.
Realistic depth of field.
High photographic detail.

Preserve the child's identity and recognizable facial features
as accurately as possible.

Do not change the child's face shape, eyes, nose, lips,
eyebrows or natural proportions.

The child must look age-appropriate and completely natural.

No adult makeup.
No adult styling.
No sexualized appearance.
No plastic skin.
No CGI.
"""
    },

    "man": {
        "name": "🤵 Мужская",
        "prompt": """
Create a premium professional men's fashion editorial portrait.

Confident masculine styling.
Sophisticated composition.
Natural masculine pose.
Professional cinematic lighting.
Premium fashion magazine aesthetic.

Professional full-frame camera look.
Extremely detailed realistic skin texture.
Natural pores.
Detailed beard or facial hair when naturally present.
Realistic clothing texture.
Natural shadows.
High dynamic range.
Realistic depth of field.

Preserve the person's identity and recognizable facial features
as accurately as possible.

Do not change the face shape, eyes, nose, lips, eyebrows,
or natural facial proportions.

Keep the person looking natural and recognizable.

Photorealistic professional photography.

No plastic skin.
No artificial beauty filter.
No CGI.
"""
    }
}


# ==========================================
# РАБОТА С ПРОМТАМИ
# ==========================================

def load_prompts():

    if not os.path.exists(PROMPTS_FILE):

        save_prompts(DEFAULT_PROMPTS)

        return DEFAULT_PROMPTS

    try:

        with open(
            PROMPTS_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

            return data

    except Exception:

        return DEFAULT_PROMPTS


def save_prompts(data):

    with open(
        PROMPTS_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )


# ==========================================
# ГЛАВНОЕ МЕНЮ
# ==========================================

def main_menu():

    prompts = load_prompts()

    buttons = []

    items = list(prompts.items())

    for i in range(0, len(items), 2):

        row = []

        for key, data in items[i:i + 2]:

            row.append(
                InlineKeyboardButton(
                    data["name"],
                    callback_data=f"style_{key}"
                )
            )

        buttons.append(row)

    return InlineKeyboardMarkup(buttons)


# ==========================================
# START
# ==========================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    context.user_data.clear()

    text = (
        "✨ AI PHOTO STUDIO\n\n"
        "Создай профессиональную фотосессию "
        "с помощью AI.\n\n"
        "Выбери стиль 👇"
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu()
    )


# ==========================================
# АДМИН-МЕНЮ
# ==========================================

def admin_menu():

    keyboard = [

        [
            InlineKeyboardButton(
                "➕ Добавить стиль",
                callback_data="admin_add"
            )
        ],

        [
            InlineKeyboardButton(
                "📋 Мои стили",
                callback_data="admin_list"
            )
        ],

        [
            InlineKeyboardButton(
                "✏️ Изменить промт",
                callback_data="admin_edit"
            )
        ],

        [
            InlineKeyboardButton(
                "🗑 Удалить стиль",
                callback_data="admin_delete"
            )
        ],

        [
            InlineKeyboardButton(
                "🏠 Главное меню",
                callback_data="main_menu"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:

        return

    await update.message.reply_text(
        "⚙️ АДМИН-ПАНЕЛЬ\n\n"
        "Здесь ты можешь управлять своими фотосессиями.",
        reply_markup=admin_menu()
    )


# ==========================================
# ОБРАБОТКА КНОПОК
# ==========================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    data = query.data

    # Главное меню

    if data == "main_menu":

        await query.message.edit_text(
            "✨ Выбери стиль фотосессии:",
            reply_markup=main_menu()
        )

        return


    # Админка

    if data.startswith("admin_"):

        if query.from_user.id != ADMIN_ID:

            return


    if data == "admin_panel":

        await query.message.edit_text(
            "⚙️ АДМИН-ПАНЕЛЬ",
            reply_markup=admin_menu()
        )

        return


    # Добавление

    if data == "admin_add":

        context.user_data["admin_action"] = "add_name"

        await query.message.reply_text(
            "➕ Добавляем новую фотосессию.\n\n"
            "Напиши название.\n\n"
            "Например:\n"
            "🌹 Красная роза"
        )

        return


    # Список

    if data == "admin_list":

        prompts = load_prompts()

        text = "📋 Твои фотосессии:\n\n"

        for key, item in prompts.items():

            text += f"• {item['name']}\n"

        await query.message.edit_text(
            text,
            reply_markup=admin_menu()
        )

        return


    # Редактирование

    if data == "admin_edit":

        prompts = load_prompts()

        keyboard = []

        for key, item in prompts.items():

            keyboard.append([
                InlineKeyboardButton(
                    item["name"],
                    callback_data=f"edit_{key}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "⬅️ Назад",
                callback_data="admin_panel"
            )
        ])

        await query.message.edit_text(
            "✏️ Выбери стиль:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return


    # Удаление

    if data == "admin_delete":

        prompts = load_prompts()

        keyboard = []

        for key, item in prompts.items():

            keyboard.append([
                InlineKeyboardButton(
                    f"🗑 {item['name']}",
                    callback_data=f"delete_{key}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "⬅️ Назад",
                callback_data="admin_panel"
            )
        ])

        await query.message.edit_text(
            "🗑 Выбери стиль для удаления:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return


    # Выбор стиля клиентом

    if data.startswith("style_"):

        style = data.replace(
            "style_",
            "",
            1
        )

        prompts = load_prompts()

        if style not in prompts:

            await query.message.reply_text(
                "Этот стиль пока недоступен."
            )

            return

        context.user_data["style"] = style
        context.user_data["waiting_photo"] = True

        await query.message.reply_text(
            f"{prompts[style]['name']}\n\n"
            "📸 Теперь отправь фотографию.\n\n"
            "Я автоматически применю выбранный стиль "
            "и постараюсь максимально сохранить твоё лицо."
        )

        return


    # Редактирование выбранного

    if data.startswith("edit_"):

        key = data.replace(
            "edit_",
            "",
            1
        )

        context.user_data["admin_action"] = "edit_prompt"
        context.user_data["edit_key"] = key

        await query.message.reply_text(
            "✏️ Отправь новый промт для этой фотосессии.\n\n"
            "Можно вставить большой промт целиком."
        )

        return


    # Удаление выбранного

    if data.startswith("delete_"):

        key = data.replace(
            "delete_",
            "",
            1
        )

        prompts = load_prompts()

        if key in prompts:

            deleted_name = prompts[key]["name"]

            del prompts[key]

            save_prompts(prompts)

            await query.message.edit_text(
                f"🗑 Удалено:\n{deleted_name}",
                reply_markup=admin_menu()
            )

        return


# ==========================================
# ТЕКСТОВЫЕ СООБЩЕНИЯ АДМИНА
# ==========================================

async def handle_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:

        return


    action = context.user_data.get(
        "admin_action"
    )


    # Название нового стиля

    if action == "add_name":

        context.user_data["new_name"] = (
            update.message.text
        )

        context.user_data["admin_action"] = (
            "add_prompt"
        )

        await update.message.reply_text(
            "Отлично 👍\n\n"
            "Теперь отправь сам промт.\n\n"
            "Можно вставить его полностью."
        )

        return


    # Промт нового стиля

    if action == "add_prompt":

        name = context.user_data.get(
            "new_name"
        )

        prompt = update.message.text

        key = (
            "custom_"
            + str(update.effective_user.id)
            + "_"
            + str(len(load_prompts()) + 1)
        )

        prompts = load_prompts()

        prompts[key] = {
            "name": name,
            "prompt": prompt
        }

        save_prompts(prompts)

        context.user_data.clear()

        await update.message.reply_text(
            "✅ Готово!\n\n"
            f"{name}\n\n"
            "Фотосессия добавлена в меню.",
            reply_markup=main_menu()
        )

        return


    # Новый промт существующего стиля

    if action == "edit_prompt":

        key = context.user_data.get(
            "edit_key"
        )

        prompts = load_prompts()

        if key in prompts:

            prompts[key]["prompt"] = (
                update.message.text
            )

            save_prompts(prompts)

            context.user_data.clear()

            await update.message.reply_text(
                "✅ Промт успешно изменён.",
                reply_markup=admin_menu()
            )

        return


# ==========================================
# ОБРАБОТКА ФОТО
# ==========================================

async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    style = context.user_data.get(
        "style"
    )

    if not style:

        await message.reply_text(
            "Сначала выбери стиль 👇",
            reply_markup=main_menu()
        )

        return


    prompts = load_prompts()

    if style not in prompts:

        await message.reply_text(
            "Этот стиль больше недоступен."
        )

        return


    await message.reply_text(
        "📸 Фотография получена!\n\n"
        "✨ Сохраняю лицо\n"
        "✨ Применяю выбранный стиль\n"
        "✨ Улучшаю фотографию\n\n"
        "Немного подожди ❤️"
    )


    try:

        if message.photo:

            photo = message.photo[-1]

            telegram_file = (
                await photo.get_file()
            )

        elif (
            message.document
            and message.document.mime_type
            and message.document.mime_type.startswith(
                "image/"
            )
        ):

            telegram_file = (
                await message.document.get_file()
            )

        else:

            await message.reply_text(
                "Пожалуйста, отправь фотографию 📷"
            )

            return


        image_bytes = (
            await telegram_file.download_as_bytearray()
        )


        image_file = io.BytesIO(
            image_bytes
        )

        image_file.name = "input.jpg"


        prompt = prompts[style]["prompt"]


        result = client.images.edit(

            model="gpt-image-2",

            image=image_file,

            prompt=prompt,

            size="1024x1536"
        )


        image_base64 = (
            result.data[0].b64_json
        )


        result_bytes = base64.b64decode(
            image_base64
        )


        await message.reply_photo(

            photo=io.BytesIO(
                result_bytes
            ),

            caption=(
                "✨ Фотосессия готова!\n\n"
                "Выбери следующий стиль 👇"
            ),

            reply_markup=main_menu()
        )


        context.user_data["style"] = None


    except Exception as error:

        print(
            "ERROR:",
            error
        )

        await message.reply_text(
            "❌ Не удалось обработать фотографию.\n\n"
            "Попробуй ещё раз."
        )


# ==========================================
# WEBHOOK
# ==========================================

@app.get("/")
async def home():

    return {
        "status": "AI Photo Studio bot is running"
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

    await telegram_app.process_update(
        update
    )

    return {
        "ok": True
    }


# ==========================================
# STARTUP
# ==========================================

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


# ==========================================
# SHUTDOWN
# ==========================================

@app.on_event("shutdown")
async def shutdown():

    await telegram_app.stop()

    await telegram_app.shutdown()


# ==========================================
# RUN
# ==========================================

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
