"""
Jarvis V2 — Claude Background Tools
Uses the locally installed Claude Code CLI for deep analysis tasks.
Groq handles fast voice conversation; Claude handles complex reasoning.
"""

import asyncio
import subprocess
import sys


async def ask_claude(prompt: str, timeout: int = 45) -> str:
    """
    Call the Claude Code CLI in non-interactive mode.
    Returns the response text, or empty string on failure.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "--print", "-p", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            print(f"  [claude] Timeout after {timeout}s", flush=True)
            return ""

        result = stdout.decode("utf-8", errors="replace").strip()
        if not result and stderr:
            err = stderr.decode("utf-8", errors="replace").strip()
            print(f"  [claude] stderr: {err[:200]}", flush=True)
        return result

    except FileNotFoundError:
        print("  [claude] CLI not found — is Claude Code installed?", flush=True)
        return ""
    except Exception as e:
        print(f"  [claude] Error: {e}", flush=True)
        return ""


async def summarize_for_jarvis(content: str, user_address: str = "Sir") -> str:
    """
    Ask Claude to summarize web/search content in Jarvis style (Hungarian, max 3 sentences).
    """
    prompt = (
        f"Te vagy Jarvis, Tony Stark AI asszisztense. "
        f"Foglald össze az alábbi információkat RÖVIDEN magyarul, maximum 3 mondatban, "
        f"száraz brit stílusban. Szólítsd a felhasználót '{user_address}'-ként. "
        f"SEMMIFÉLE szögletes zárójelben lévő tag vagy ACTION tag.\n\n"
        f"Összefoglalandó:\n{content[:3000]}"
    )
    result = await ask_claude(prompt)
    return result


async def deep_answer(question: str, user_address: str = "Sir") -> str:
    """
    Ask Claude a complex question directly (no web search).
    Used as fallback when Groq rate-limits or for complex reasoning.
    """
    prompt = (
        f"Te vagy Jarvis, Tony Stark AI asszisztense. "
        f"A gazdád Károly, akit '{user_address}'-nak szólítasz. "
        f"Kizárólag magyarul válaszolj. Maximum 3 mondat. "
        f"Száraz, szarkasztikus brit stílus. SEMMIFÉLE tag vagy ACTION.\n\n"
        f"Kérdés: {question}"
    )
    return await ask_claude(prompt)
