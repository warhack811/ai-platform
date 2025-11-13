from typing import Optional
import re

import httpx

OLLAMA_MODEL = "dolphin-my-gguf"
OLLAMA_TIMEOUT = 120


async def chat_ollama(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
    max_tokens: int = 400
) -> str:
    """Ollama ile text üretimi"""
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            response = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                        "num_ctx": 2048,
                        "num_thread": 4,
                    }
                }
            )

            if response.status_code == 200:
                result = response.json().get("response", "")
                # Düşünme taglerini temizle
                result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL)
                result = re.sub(r'<reasoning>.*?</reasoning>', '', result, flags=re.DOTALL)
                return result.strip() or "Cevap üretilemedi."
            else:
                return f"Ollama HTTP {response.status_code}"

    except httpx.TimeoutException:
        return "⏱️ Timeout - Lütfen daha kısa bir soru deneyin."
    except Exception as e:
        return f"❌ {str(e)}"
