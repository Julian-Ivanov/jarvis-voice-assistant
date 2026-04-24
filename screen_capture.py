"""
Jarvis V2 — Screen Capture
Takes screenshots and describes them via Groq Vision (Llama).
"""

import base64
import io
from PIL import ImageGrab


def capture_screen() -> bytes:
    """Capture the entire screen, return PNG bytes."""
    img = ImageGrab.grab()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def describe_screen(groq_client) -> str:
    """Capture screen and describe it using Groq Vision."""
    png_bytes = capture_screen()
    b64 = base64.b64encode(png_bytes).decode("utf-8")

    response = await groq_client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{b64}"
                    }
                },
                {
                    "type": "text",
                    "text": "Írd le röviden magyarul mit látsz ezen a képernyőn. Maximum 2-3 mondat. Nevezd meg a legfontosabb nyitott programokat és tartalmakat."
                }
            ]
        }]
    )
    return response.choices[0].message.content
