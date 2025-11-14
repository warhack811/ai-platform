from typing import Optional, AsyncGenerator
import re
import httpx

OLLAMA_MODEL = "dolphin-my-gguf"
OLLAMA_TIMEOUT = 180


async def chat_ollama(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
    max_tokens: int = 1500
) -> str:
    """Ollama ile text üretimi (normal)"""
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
                        "num_ctx": 8192,
                        "num_thread": 8,
                        "top_p": 0.9,     # Daha çeşitli cevaplar
                        "top_k": 40,
                        "repeat_penalty": 1.15  # Tekrarı önle
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


async def chat_ollama_stream(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
    max_tokens: int = 400
) -> AsyncGenerator[str, None]:
    """Ollama ile streaming text üretimi (kelime kelime)"""
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            async with client.stream(
                "POST",
                "http://localhost:11434/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "system": system,
                    "stream": True,  # ← Streaming aktif
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                        "num_ctx": 2048,
                        "num_thread": 4,
                    }
                }
            ) as response:
                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            import json
                            chunk = json.loads(line)
                            text = chunk.get("response", "")
                            
                            # Düşünme taglerini filtrele
                            if "<think>" not in text and "<reasoning>" not in text:
                                yield text
                            
                            # Cevap bitti mi?
                            if chunk.get("done", False):
                                break
                        except:
                            continue
    except Exception as e:
        yield f"\n\n❌ Hata: {str(e)}"