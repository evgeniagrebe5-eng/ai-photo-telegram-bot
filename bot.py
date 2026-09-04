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
    
