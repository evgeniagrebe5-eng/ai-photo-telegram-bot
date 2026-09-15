QUALITY_BLOCK = """
Photorealistic professional photography. Preserve the person's identity exactly from the uploaded client photo.
Natural skin texture, realistic pores, natural eyes, realistic hair strands, realistic hands and fingers,
accurate anatomy, realistic fabric and materials, physically accurate lighting and shadows, natural reflections,
professional full-frame camera look, crisp fine detail, editorial photography quality.
Do not change identity, age, facial proportions or distinctive features. No plastic skin, beauty filter, CGI,
3D-rendered look, cartoon look, artificial face smoothing, warped anatomy or distorted hands.
"""

DEFAULT_PROMPTS = {
    "autumn": f"""Create a premium autumn fashion editorial using the uploaded client photo as the strict identity reference.
Warm autumn palette, elegant seasonal styling, golden foliage, sophisticated outdoor location, natural confident pose,
cinematic composition, soft directional daylight, realistic depth and professional editorial finish.
{QUALITY_BLOCK}""",

    "winter": f"""Create a premium winter fashion editorial using the uploaded client photo as the strict identity reference.
Elegant winter styling, sophisticated coat and layered textures, refined snowy or winter architectural setting,
cinematic cold-season atmosphere, natural pose, beautiful controlled light and realistic snow/material detail.
{QUALITY_BLOCK}""",

    "author": f"""Create an original high-end editorial photoshoot from the uploaded client photo.
Use a strong artistic visual concept, an unusual but believable location or visual element, sophisticated styling,
clear composition, cinematic lighting and a premium contemporary-art fashion aesthetic.
{QUALITY_BLOCK}""",

    "couples": f"""Create a professional couples editorial photo using the uploaded people as strict identity references.
Preserve each person's identity and age. Natural affectionate interaction, elegant styling, believable body language,
cinematic composition, premium location and realistic lighting. No exaggerated romance or artificial expressions.
{QUALITY_BLOCK}""",

    "women_portrait": f"""Create a premium women's portrait editorial using the uploaded client photo as the strict identity reference.
Elegant styling, sophisticated background, flattering professional portrait lighting, natural expression,
realistic skin and hair detail, refined magazine composition.
{QUALITY_BLOCK}""",

    "men_portrait": f"""Create a premium men's portrait editorial using the uploaded client photo as the strict identity reference.
Modern masculine styling, sophisticated location, confident natural pose, cinematic directional lighting,
realistic skin, hair, beard and clothing texture, professional magazine composition.
{QUALITY_BLOCK}""",

    "studio": f"""Create a professional studio editorial portrait using the uploaded client photo as the strict identity reference.
Minimal premium studio set, controlled professional lighting, elegant styling, precise composition,
realistic shadows and high-end commercial photography finish.
{QUALITY_BLOCK}""",

    "stickers": f"""Create a polished sticker-style portrait based on the uploaded client photo while keeping the person's identity recognizable.
Clean isolated composition, expressive but natural pose, crisp edges and professional commercial sticker aesthetics.
Avoid changing the person's distinctive facial characteristics.
{QUALITY_BLOCK}""",

    "humor": f"""Create a tasteful humorous editorial image based on the uploaded client photo.
Keep the person's identity recognizable and natural. Use one clear visual joke or playful situation,
with professional cinematic photography, believable props and excellent composition.
{QUALITY_BLOCK}""",
}

TITLES = {
    "autumn": "🍂 Осенние образы",
    "winter": "❄️ Зимние образы",
    "author": "✨ Авторский промт",
    "couples": "💞 Парные фото",
    "women_portrait": "👩 Портреты женские",
    "men_portrait": "👨 Портреты мужские",
    "studio": "🎬 Студийные фото",
    "stickers": "🎀 Стикеры",
    "humor": "😂 Юмористические фото",
}
