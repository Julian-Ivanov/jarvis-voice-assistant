"""
Jarvis V2 — Screen Capture
Takes screenshots and describes them via Claude Vision.
"""

import asyncio
import base64
import io
from PIL import ImageGrab


def capture_screen() -> bytes:
    """Capture the entire screen, return PNG bytes (downscaled to fit Anthropic image limits)."""
    img = ImageGrab.grab()
    img.thumbnail((1568, 1568))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def describe_screen(anthropic_client) -> str:
    """Capture screen and describe it using Claude Vision."""
    png_bytes = await asyncio.to_thread(capture_screen)
    b64 = base64.b64encode(png_bytes).decode("utf-8")

    response = await anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64,
                    },
                },
                {
                    "type": "text",
                    "text": "Briefly describe what's on this screen. Max 2-3 sentences. Name the most important open apps and content. Reply in German by default — if the original question was clearly English, reply in English.",
                },
            ],
        }],
    )
    return response.content[0].text
