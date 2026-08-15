"""
Jarvis V2 — Translation via Claude itself (no extra API).
Supports DE/EN/FR. Uses Claude Haiku — same client as the rest of server.py.
"""

LANG_NAME = {
    "de": "Deutsch",
    "en": "English",
    "fr": "français",
}


async def translate(anthropic_client, text: str, target_lang: str, source_lang: str | None = None) -> str:
    """Translate `text` into `target_lang`. Returns the translation only — no commentary."""
    target_lang = target_lang.lower().strip()
    if target_lang not in LANG_NAME:
        raise ValueError(f"Unsupported target language: {target_lang}. Use de|en|fr.")

    target_name = LANG_NAME[target_lang]
    source_clause = (
        f"The source language is {LANG_NAME.get(source_lang.lower(), source_lang)}."
        if source_lang else "Auto-detect the source language."
    )

    prompt = (
        f"Translate the following text into {target_name}. {source_clause} "
        "Reply with only the translation — no quotes, no commentary, no source-text echo. "
        "Preserve formatting (line breaks, lists, markdown). Keep proper nouns and brand names unchanged.\n\n"
        f"---\n{text}\n---"
    )

    response = await anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
