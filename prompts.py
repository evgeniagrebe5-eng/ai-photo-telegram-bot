PHOTO_SESSIONS = {
    "autumn": {
        "title": "🍂 Осенняя",
        "prompt": "",
    },
    "luxury": {
        "title": "💎 Luxury",
        "prompt": "",
    },
    "fashion": {
        "title": "👠 Fashion",
        "prompt": "",
    },
    "love_story": {
        "title": "❤️ Love Story",
        "prompt": "",
    },
    "romantic": {
        "title": "🌸 Romantic",
        "prompt": "",
    },
    "black_editorial": {
        "title": "🖤 Black Editorial",
        "prompt": "",
    },
    "children": {
        "title": "👶 Детская фотосессия",
        "prompt": "",
    },
    "men": {
        "title": "👨 Мужская фотосессия",
        "prompt": "",
    },
}


def get_session(session_id):
    return PHOTO_SESSIONS.get(session_id)


def get_all_sessions():
    return PHOTO_SESSIONS
#
# Этот файл пока НЕ подключён к боту.
# Мы сначала создаём безопасную основу для будущего управления промтами.

