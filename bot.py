import os
import io
import json
import asyncio
import logging
from contextlib import asynccontextmanager

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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ADMIN_ID = os.environ.get("ADMIN_ID")

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


# =========================================================
# OPENAI
# =========================================================

client = OpenAI(api_key=OPENAI_API_KEY)


# =========================================================
# ФОТОСЕССИИ ПО УМОЛЧАНИЮ
# =========================================================

DEFAULT_SESSIONS = {
    "autumn": {
        "title": "🍂 Осенняя",
        "prompt": """
Создай профессиональную фотореалистичную осеннюю fashion-фотосессию,
используя загруженную фотографию человека как строгий референс личности.

Сохрани идентичность человека максимально точно:
форму лица, пропорции, глаза, нос, губы, брови и индивидуальные особенности.
Не меняй возраст и внешность человека.

Осенняя атмосфера, натуральная золотистая листва, теплые оттенки,
красивая композиция, естественная поза, живое движение,
дорогая fashion-съемка, реалистичная кожа с естественной текстурой,
детальная одежда и волосы.

Профессиональная камера, физически корректный свет,
мягкий естественный объемный свет, реалистичные тени,
кинематографическая глубина резкости.

Фотореализм высокого уровня.
Без пластиковой кожи, без чрезмерного сглаживания,
без изменения лица, без эффекта CGI, без мультяшности.
""",
    },

    "luxury": {
        "title": "💎 Luxury",
        "prompt": """
Создай роскошную профессиональную fashion-фотографию человека
на основе загруженного изображения.

Максимально точно сохрани личность и черты лица человека.
Не меняй форму лица, пропорции, глаза, нос, губы, брови
и индивидуальные особенности внешности.

Эстетика luxury editorial:
дорогой образ, премиальная атмосфера, изысканный интерьер,
элегантная одежда, дорогие фактуры, стильная композиция.

Профессиональная журнальная фотосъемка,
реалистичная кожа, естественная текстура кожи,
детальная ткань, реалистичные волосы.

Мягкий направленный студийный свет,
глубокие естественные тени, красивый объем,
профессиональная оптика, малая глубина резкости.

Очень высокий фотореализм.
Без пластиковой кожи, beauty-фильтров,
изменения личности, CGI и мультяшного эффекта.
""",
    },

    "fashion": {
        "title": "👠 Fashion",
        "prompt": """
Создай современную профессиональную fashion-фотографию
на основе загруженного изображения человека.

Сохрани идентичность человека максимально точно.
Не изменяй черты лица, пропорции и индивидуальные особенности.

Стиль современной fashion editorial съемки:
уверенная поза, динамичная композиция,
стильная одежда, дорогой fashion-образ,
профессиональная постановка.

Изображение должно выглядеть как настоящая съемка
профессионального fashion-фотографа.

Реалистичная кожа с естественной текстурой,
детальная ткань, реалистичные волосы,
естественные руки и пальцы.

Профессиональный свет, объемные тени,
реалистичная оптика, естественная глубина резкости.

Максимальный фотореализм.
Не использовать пластиковую кожу,
чрезмерное сглаживание, CGI или мультяшность.
""",
    },

    "love": {
        "title": "❤️ Love Story",
        "prompt": """
Создай романтическую профессиональную фотографию
в стиле Love Story на основе загруженного изображения.

Если на референсе один человек, сохрани его идентичность максимально точно.
Если присутствуют два человека, сохрани идентичность каждого.

Не изменяй черты лица, пропорции и индивидуальные особенности.

Теплая романтическая атмосфера,
естественные эмоции, живое взаимодействие,
кинематографическая композиция,
красивый естественный фон.

Профессиональная фотосъемка,
мягкий естественный свет,
реалистичная кожа, натуральная текстура,
детальная одежда и волосы.

Фотореализм высокого уровня.
Без пластиковой кожи, beauty-фильтров,
изменения лиц, CGI и мультяшности.
""",
    },

    "romantic": {
        "title": "🌸 Romantic",
        "prompt": """
Создай нежную романтическую fashion-фотографию
на основе загруженного изображения человека.

Сохрани идентичность человека максимально точно.
Не изменяй форму лица, глаза, нос, губы, брови
и другие индивидуальные особенности.

Нежная романтическая атмосфера,
элегантный образ, мягкие детали,
естественная поза, воздушная композиция.

Профессиональная editorial фотосъемка,
мягкий объемный свет,
реалистичная кожа с естественной текстурой,
реалистичные волосы и ткани.

Красивое естественное боке,
профессиональная оптика,
физически корректное освещение.

Максимальный фотореализм.
Без пластиковой кожи, чрезмерного сглаживания,
изменения лица, CGI и мультяшности.
""",
    },

    "black": {
        "title": "🖤 Black Editorial",
        "prompt": """
Создай профессиональную драматичную fashion editorial фотографию
на основе загруженного изображения человека.

Максимально точно сохрани личность человека,
его лицо, пропорции и индивидуальные особенности.

Черная эстетика editorial:
темный стиль, элегантная одежда,
минималистичная композиция,
выразительная поза, дорогая fashion-атмосфера.

Контрастный профессиональный свет,
объемные естественные тени,
кинематографическая глубина,
реалистичная кожа и фактура одежды.

Профессиональная full-frame камера,
дорогая оптика, реалистичная глубина резкости.

Максимальный фотореализм.
Без изменения лица, пластиковой кожи,
beauty-фильтров, CGI и мультяшности.
""",
    },

    "child": {
        "title": "👶 Детская фотосессия",
        "prompt": """
Создай профессиональную детскую фотосессию
на основе загруженной фотографии ребенка.

Максимально точно сохрани внешность и идентичность ребенка.
Не изменяй лицо, форму глаз, нос, губы,
пропорции лица и индивидуальные особенности.

Создай красивую профессиональную фотосессию,
естественную детскую позу и живые эмоции.

Мягкий красивый свет,
естественная кожа с натуральной текстурой,
реалистичные волосы и одежда,
профессиональная композиция.

Изображение должно выглядеть как настоящая фотография,
снятая профессиональным детским фотографом.

Без пластиковой кожи,
без изменения внешности,
без мультяшности и CGI.
""",
    },

    "man": {
        "title": "🤵 Мужская фотосессия",
        "prompt": """
Создай профессиональную мужскую fashion-фотосессию
на основе загруженной фотографии.

Максимально точно сохрани личность и внешность мужчины.
Не изменяй лицо, пропорции, глаза, нос, губы,
бороду и индивидуальные особенности.

Стиль современной мужской editorial фотосъемки:
уверенная естественная поза,
дорогой мужской образ,
стильная одежда,
профессиональная композиция.

Реалистичная кожа с естественной текстурой,
детальная одежда,
реалистичные волосы и борода.

Профессиональное освещение,
объемные естественные тени,
кинематографическая глубина резкости,
дорогая оптика.

Максимальный фотореализм.
Без пластиковой кожи,
beauty-фильтров, изменения лица,
CGI и мультяшного эффекта.
""",
    },
}


# =========================================================
# ХРАНЕНИЕ ПРОМТОВ
# =========================================================

PROMPTS_FILE = "prompts.json"


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


def save_sessions(data):
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


SESSIONS = load_sessions()


# =========================================================
# TELEGRAM APPLICATION
# =========================================================

telegram_app = (
    Application.builder()
    .token(BOT_TOKEN)
    .build()
)


# =========================================================
# КЛАВИАТУРА КЛИЕНТА
# =========================================================

def client_keyboard():
    buttons = []

    for key, session in SESSIONS.items():
        buttons.append(
            [
                InlineKeyboardButton(
                    session["title"],
                    callback_data=f"style:{key}",
                )
            ]
        )

    return InlineKeyboardMarkup(buttons)


# =========================================================
# КЛАВИАТУРА АДМИНИСТРАТОРА
# =========================================================

def admin_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ Добавить фотосессию",
                    callback_data="admin:add",
                )
            ],
            [
                InlineKeyboardButton(
                    "✏️ Изменить промт",
                    callback_data="admin:edit",
                )
            ],
            [
                InlineKeyboardButton(
                    "🗑 Удалить фотосессию",
                    callback_data="admin:delete",
                )
            ],
            [
                InlineKeyboardButton(
                    "📋 Мои фотосессии",
                    callback_data="admin:list",
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 Главное меню",
                    callback_data="admin:home",
                )
            ],
        ]
    )


# =========================================================
# ПРОВЕРКА АДМИНА
# =========================================================

def is_admin(update: Update):
    user = update.effective_user

    if not user:
        return False

    return user.id == ADMIN_ID


# =========================================================
# /START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    text = (
        "✨ Добро пожаловать в AI Photo Gallery!\n\n"
        "Выбери фотосессию 👇\n\n"
        "После выбора просто отправь фотографию 📸\n"
        "Промт писать не нужно — я всё сделаю сама ❤️"
    )

    await update.message.reply_text(
        text,
        reply_markup=client_keyboard(),
    )


# =========================================================
# /ADMIN
# =========================================================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text(
            "⛔ У вас нет доступа к админ-панели."
        )
        return

    context.user_data.clear()

    await update.message.reply_text(
        "👑 Панель администратора\n\n"
        "Выбери действие:",
        reply_markup=admin_keyboard(),
    )


# =========================================================
# CALLBACK
# =========================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    await query.answer()

    data = query.data

    # -----------------------------------------------------
    # ВЫБОР ФОТОСЕССИИ КЛИЕНТОМ
    # -----------------------------------------------------

    if data.startswith("style:"):
        key = data.split(":", 1)[1]

        if key not in SESSIONS:
            await query.message.reply_text(
                "❌ Эта фотосессия больше недоступна."
            )
            return

        context.user_data["selected_style"] = key

        title = SESSIONS[key]["title"]

        await query.message.reply_text(
            f"{title}\n\n"
            "Отлично ❤️\n"
            "Теперь просто отправь свою фотографию 📸\n\n"
            "Промт писать не нужно."
        )

        return

    # -----------------------------------------------------
    # АДМИН
    # -----------------------------------------------------

    if not is_admin(update):
        return

    # Главное меню админа
    if data == "admin:home":
        context.user_data.clear()

        await query.message.reply_text(
            "👑 Панель администратора\n\n"
            "Выбери действие:",
            reply_markup=admin_keyboard(),
        )

        return

    # Добавление
    if data == "admin:add":
        context.user_data.clear()
        context.user_data["admin_state"] = "add_title"

        await query.message.reply_text(
            "➕ Добавление фотосессии\n\n"
            "Шаг 1 из 2.\n\n"
            "Напиши название новой фотосессии.\n\n"
            "Например:\n"
            "🌊 Морская фотосессия"
        )

        return

    # Изменение
    if data == "admin:edit":
        if not SESSIONS:
            await query.message.reply_text(
                "Пока нет фотосессий."
            )
            return

        buttons = []

        for key, session in SESSIONS.items():
            buttons.append(
                [
                    InlineKeyboardButton(
                        session["title"],
                        callback_data=f"edit:{key}",
                    )
                ]
            )

        buttons.append(
            [
                InlineKeyboardButton(
                    "🔙 Назад",
                    callback_data="admin:home",
                )
            ]
        )

        await query.message.reply_text(
            "✏️ Выбери фотосессию, промт которой нужно изменить:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

        return

    # Удаление
    if data == "admin:delete":
        if not SESSIONS:
            await query.message.reply_text(
                "Пока нет фотосессий."
            )
            return

        buttons = []

        for key, session in SESSIONS.items():
            buttons.append(
                [
                    InlineKeyboardButton(
                        f"🗑 {session['title']}",
                        callback_data=f"delete:{key}",
                    )
                ]
            )

        buttons.append(
            [
                InlineKeyboardButton(
                    "🔙 Назад",
                    callback_data="admin:home",
                )
            ]
        )

        await query.message.reply_text(
            "🗑 Выбери фотосессию для удаления:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

        return

    # Список
    if data == "admin:list":
        if not SESSIONS:
            text = "📋 Фотосессий пока нет."
        else:
            lines = ["📋 Твои фотосессии:\n"]

            for index, session in enumerate(
                SESSIONS.values(),
                start=1,
            ):
                lines.append(
                    f"{index}. {session['title']}"
                )

            text = "\n".join(lines)

        await query.message.reply_text(
            text,
            reply_markup=admin_keyboard(),
        )

        return

    # -----------------------------------------------------
    # ВЫБРАНА ФОТОСЕССИЯ ДЛЯ РЕДАКТИРОВАНИЯ
    # -----------------------------------------------------

    if data.startswith("edit:"):
        key = data.split(":", 1)[1]

        if key not in SESSIONS:
            await query.message.reply_text(
                "❌ Фотосессия не найдена."
            )
            return

        context.user_data["admin_state"] = "edit_prompt"
        context.user_data["edit_key"] = key

        await query.message.reply_text(
            f"✏️ Изменяем:\n"
            f"{SESSIONS[key]['title']}\n\n"
            "Отправь новый промт одним сообщением."
        )

        return

    # -----------------------------------------------------
    # ВЫБРАНА ФОТОСЕССИЯ ДЛЯ УДАЛЕНИЯ
    # -----------------------------------------------------

    if data.startswith("delete:"):
        key = data.split(":", 1)[1]

        if key not in SESSIONS:
            await query.message.reply_text(
                "❌ Фотосессия не найдена."
            )
            return

        title = SESSIONS[key]["title"]

        del SESSIONS[key]
        save_sessions(SESSIONS)

        await query.message.reply_text(
            f"🗑 Удалено:\n{title}",
            reply_markup=admin_keyboard(),
        )

        return


# =========================================================
# ТЕКСТОВЫЕ СООБЩЕНИЯ АДМИНА
# =========================================================

async def admin_text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(update):
        return

    state = context.user_data.get("admin_state")

    if not state:
        return

    text = update.message.text.strip()

    # -----------------------------------------------------
    # НОВАЯ ФОТОСЕССИЯ — НАЗВАНИЕ
    # -----------------------------------------------------

    if state == "add_title":
        context.user_data["new_title"] = text
        context.user_data["admin_state"] = "add_prompt"

        await update.message.reply_text(
            "✅ Название сохранено.\n\n"
            "Шаг 2 из 2.\n\n"
            "Теперь отправь промт для этой фотосессии."
        )

        return

    # -----------------------------------------------------
    # НОВАЯ ФОТОСЕССИЯ — ПРОМТ
    # -----------------------------------------------------

    if state == "add_prompt":
        title = context.user_data.get("new_title")

        key = f"custom_{len(SESSIONS) + 1}"

        SESSIONS[key] = {
            "title": title,
            "prompt": text,
        }

        save_sessions(SESSIONS)

        context.user_data.clear()

        await update.message.reply_text(
            f"✅ Новая фотосессия создана!\n\n"
            f"{title}\n\n"
            "Теперь она появилась в меню клиентов.",
            reply_markup=admin_keyboard(),
        )

        return

    # -----------------------------------------------------
    # РЕДАКТИРОВАНИЕ ПРОМТА
    # -----------------------------------------------------

    if state == "edit_prompt":
        key = context.user_data.get("edit_key")

        if not key or key not in SESSIONS:
            context.user_data.clear()

            await update.message.reply_text(
                "❌ Не удалось найти фотосессию.",
                reply_markup=admin_keyboard(),
            )

            return

        SESSIONS[key]["prompt"] = text

        save_sessions(SESSIONS)

        title = SESSIONS[key]["title"]

        context.user_data.clear()

        await update.message.reply_text(
            f"✅ Промт обновлён!\n\n"
            f"{title}",
            reply_markup=admin_keyboard(),
        )

        return


# =========================================================
# ГЕНЕРАЦИЯ ФОТО
# =========================================================

async def photo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    style = context.user_data.get("selected_style")

    if not style:
        await update.message.reply_text(
            "Сначала выбери фотосессию 👇",
            reply_markup=client_keyboard(),
        )
        return

    if style not in SESSIONS:
        await update.message.reply_text(
            "❌ Эта фотосессия больше недоступна.",
            reply_markup=client_keyboard(),
        )
        return

    session = SESSIONS[style]
    prompt = session["prompt"]

    await update.message.reply_text(
        "📸 Фото получила!\n\n"
        "✨ Начинаю обработку...\n"
        "Это может занять некоторое время."
    )

    try:
        telegram_file = await update.message.photo[-1].get_file()

        photo_bytes = await telegram_file.download_as_bytearray()

        image_file = io.BytesIO(bytes(photo_bytes))
        image_file.name = "photo.jpg"

        def generate_image():
            return client.images.edit(
                model="gpt-image-2",
                image=image_file,
                prompt=prompt,
                size="1024x1536",
            )

        result = await asyncio.to_thread(
            generate_image
        )

        if not result.data:
            raise RuntimeError(
                "OpenAI returned no image"
            )

        image_data = result.data[0]

        if not getattr(image_data, "b64_json", None):
            raise RuntimeError(
                "OpenAI returned no b64_json"
            )

        import base64

        generated_bytes = base64.b64decode(
            image_data.b64_json
        )

        output = io.BytesIO(generated_bytes)
        output.name = "ai_photo.png"

        await update.message.reply_photo(
            photo=output,
            caption=(
                f"✨ Готово!\n\n"
                f"{session['title']}\n\n"
                "Хочешь ещё фото? "
                "Выбери другую фотосессию 👇"
            ),
            reply_markup=client_keyboard(),
        )

    except Exception as e:
        logger.exception(
            "Image generation error"
        )

        await update.message.reply_text(
            "😔 Не удалось создать фотографию.\n\n"
            "Попробуй отправить фото ещё раз."
        )


# =========================================================
# ОБРАБОТЧИК НЕПОНЯТНОГО ТЕКСТА
# =========================================================

async def unknown_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if is_admin(update):
        if context.user_data.get("admin_state"):
            return

    await update.message.reply_text(
        "Выбери фотосессию 👇",
        reply_markup=client_keyboard(),
    )


# =========================================================
# РЕГИСТРАЦИЯ TELEGRAM HANDLERS
# =========================================================

telegram_app.add_handler(
    CommandHandler("start", start)
)

telegram_app.add_handler(
    CommandHandler("admin", admin_command)
)

telegram_app.add_handler(
    CallbackQueryHandler(callback_handler)
)

telegram_app.add_handler(
    MessageHandler(
        filters.PHOTO,
        photo_handler,
    )
)

telegram_app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_text_handler,
    )
)

telegram_app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        unknown_text,
    )
)


# =========================================================
# FASTAPI LIFESPAN
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Starting Telegram application...")

    await telegram_app.initialize()
    await telegram_app.start()

    render_url = os.environ.get(
        "RENDER_EXTERNAL_URL"
    )

    if render_url:
        render_url = render_url.rstrip("/")

        webhook_url = (
            f"{render_url}/telegram"
        )

        await telegram_app.bot.set_webhook(
            webhook_url
        )

        logger.info(
            "Webhook set: %s",
            webhook_url,
        )

    else:
        logger.warning(
            "RENDER_EXTERNAL_URL is not set"
        )

    logger.info(
        "Telegram application started"
    )

    yield

    logger.info(
        "Stopping Telegram application..."
    )

    try:
        await telegram_app.bot.delete_webhook()
    except Exception:
        logger.exception(
            "Could not delete webhook"
        )

    await telegram_app.stop()
    await telegram_app.shutdown()

    logger.info(
        "Telegram application stopped"
    )


# =========================================================
# FASTAPI
# =========================================================

app = FastAPI(
    lifespan=lifespan
)


@app.get("/")
async def health():
    return {
        "status": "ok",
        "bot": "AI Photo Gallery",
    }


@app.post("/telegram")
async def telegram_webhook(request: Request):

    data = await request.json()

    update = Update.de_json(
        data,
        telegram_app.bot,
    )

    await telegram_app.process_update(
        update
    )

    return {
        "ok": True
    }


# =========================================================
# ЗАПУСК
# =========================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.environ.get(
            "PORT",
            "10000",
        )
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
    )

    
