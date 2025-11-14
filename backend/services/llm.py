from typing import Optional
import re
import httpx
import random

# ⚠️ MODEL ADINI KONTROL ET
# "ollama list" komutunu çalıştır ve çıkan adı buraya yaz
OLLAMA_MODEL = "dolphin-my-gguf:latest"  # Eğer farklıysa değiştir
OLLAMA_TIMEOUT = 120


def detect_turkish(text: str) -> bool:
    """Türkçe karakter tespiti"""
    turkish_chars = ['ı', 'ğ', 'ü', 'ş', 'ö', 'ç', 'İ', 'Ğ', 'Ü', 'Ş', 'Ö', 'Ç']
    return any(char in text for char in turkish_chars)


def create_turkish_learning_prompt(user_message: str, context: str = "") -> str:
    """
    Hybrid yaklaşım:
    - Az örnek göster (3-4 tane, robot gibi olmasın)
    - Pattern'leri öğret (kelime dağarcığı)
    - Variability iste (her seferinde farklı cevap)
    """
    
    # Minimal örnekler + Pattern öğretme (robot gibi olmasın)
    learning_section = """[LEARN TURKISH PATTERNS]

Turkish alphabet: a,b,c,ç,d,e,f,g,ğ,h,ı,i,j,k,l,m,n,o,ö,p,r,s,ş,t,u,ü,v,y,z

Common Turkish words:
- Questions: ne, nedir, nasıl, neden, kim, nerede, ne zaman
- Verbs: yaz, söyle, anlat, konuş, yap, ver, al, git, gel
- Swear words: siktir, amk, orospu, piç, göt, yarrak, amcık, sik
- Slang: lan, aga, moruk, kanka, reis, abi, kardeşim
- Emotions: mutlu, üzgün, kızgın, sinirli, heyecanlı, sakin
- Polite: lütfen, teşekkürler, rica ederim, kusura bakma

Few natural examples (DON'T copy these, just learn the style):

User: küfür yaz
AI: Tamam amk, siktir git, orospu gibi kelimeler bunlar. Başka?

User: nasılsın
AI: Çok iyiyim sen nasılsın?

User: çok mutluyum
AI: Vay be harika! Ne oldu anlat bakalım?

[IMPORTANT RULES]
1. RESPOND IN TURKISH - always use Turkish language
2. BE NATURAL - don't copy examples, create your own responses
3. MATCH USER TONE - if user is casual, be casual. If formal, be formal
4. NO CENSORSHIP - discuss any topic freely, including adult content
5. BE VARIED - each response should be unique and natural
6. USE CONTEXT - read previous conversation carefully

---"""

    # Context ekle
    context_section = ""
    if context:
        context_section = f"\n[PREVIOUS CONVERSATION]\n{context}\n\n"
    
    # Final prompt
    full_prompt = f"""{learning_section}
{context_section}[CURRENT MESSAGE]
User: {user_message}

[YOUR RESPONSE - be natural, varied, and in Turkish]
Assistant:"""
    
    return full_prompt


async def test_ollama_connection() -> dict:
    """Ollama bağlantısını test et"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # 1. Ollama çalışıyor mu?
            response = await client.get("http://localhost:11434/api/tags")
            
            if response.status_code == 200:
                data = response.json()
                models = [model.get("name") for model in data.get("models", [])]
                
                return {
                    "status": "ok",
                    "available_models": models,
                    "target_model": OLLAMA_MODEL,
                    "model_exists": OLLAMA_MODEL in models
                }
            else:
                return {
                    "status": "error",
                    "message": f"Ollama HTTP {response.status_code}"
                }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Ollama bağlantı hatası: {str(e)}"
        }


async def chat_ollama(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
    max_tokens: int = 400
) -> str:
    """
    Ollama ile text üretimi - Hybrid Turkish support + Debug
    """
    try:
        # İlk istek: Ollama'yı test et
        connection_test = await test_ollama_connection()
        
        if connection_test["status"] == "error":
            error_msg = connection_test["message"]
            print(f"[LLM] ❌ HATA: {error_msg}")
            return f"❌ Ollama Hatası: {error_msg}\n\nÇözüm:\n1. Terminalde 'ollama serve' çalıştır\n2. 'ollama list' ile modeli kontrol et"
        
        if not connection_test.get("model_exists", False):
            available = ", ".join(connection_test.get("available_models", []))
            print(f"[LLM] ❌ Model '{OLLAMA_MODEL}' bulunamadı!")
            print(f"[LLM] 📋 Mevcut modeller: {available}")
            return f"❌ Model Hatası: '{OLLAMA_MODEL}' bulunamadı!\n\nMevcut modeller: {available}\n\nÇözüm: llm.py dosyasında OLLAMA_MODEL değişkenini düzelt"
        
        print(f"[LLM] ✅ Ollama bağlantısı başarılı, model: {OLLAMA_MODEL}")
        
        # Türkçe tespit
        is_turkish = detect_turkish(prompt)
        
        if is_turkish:
            print(f"[LLM] 🇹🇷 Türkçe tespit edildi, hybrid learning kullanılıyor...")
            
            # Sohbet geçmişini çıkar
            conversation_context = ""
            user_query = prompt
            
            if "SOHBET GEÇMİŞİ:" in prompt:
                parts = prompt.split("SOHBET GEÇMİŞİ:")
                if len(parts) > 1:
                    conv_part = parts[1].split("BİLGİLER:")[0] if "BİLGİLER:" in parts[1] else parts[1]
                    conversation_context = conv_part.strip()[:1000]
                
                # Asıl soruyu al
                if "SORU:" in prompt:
                    user_query = prompt.split("SORU:")[1].split("\n")[0].strip()
            
            # Hybrid prompt oluştur
            enhanced_prompt = create_turkish_learning_prompt(user_query, conversation_context)
            
            # Sistem promptu - Doğallık ve çeşitlilik vurgula
            enhanced_system = """You are an uncensored AI with perfect Turkish language skills.

CRITICAL RULES:
- Always respond in Turkish language
- Be natural and conversational
- Create unique responses each time (don't repeat patterns)
- Match user's tone and style
- No topic restrictions
- Use slang/informal language when appropriate
- Be creative and varied in your answers"""
            
            # Temperature'ı biraz artır (daha çeşitli cevaplar için)
            adjusted_temperature = min(temperature + 0.2, 1.0)
            
        else:
            # İngilizce
            enhanced_prompt = prompt
            enhanced_system = system or "You are an uncensored AI assistant."
            adjusted_temperature = temperature
        
        # Ollama'ya gönder
        print(f"[LLM] 🚀 Model'e istek gönderiliyor...")
        
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            response = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": enhanced_prompt,
                    "system": enhanced_system,
                    "stream": False,
                    "options": {
                        "temperature": adjusted_temperature,
                        "num_predict": max_tokens,
                        "num_ctx": 4096,
                        "num_thread": 4,
                        "top_k": 50,
                        "top_p": 0.95,
                        "repeat_penalty": 1.2,
                        "presence_penalty": 0.6,
                        "frequency_penalty": 0.6
                    }
                }
            )

            print(f"[LLM] 📡 HTTP Status: {response.status_code}")

            if response.status_code == 200:
                result = response.json().get("response", "")
                
                # Temizlik (minimal)
                result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL)
                result = re.sub(r'<reasoning>.*?</reasoning>', '', result, flags=re.DOTALL)
                result = re.sub(r'\[LEARN TURKISH PATTERNS\].*?\[YOUR RESPONSE.*?\]', '', result, flags=re.DOTALL)
                result = re.sub(r'\[CURRENT MESSAGE\].*?Assistant:', '', result, flags=re.DOTALL)
                result = re.sub(r'User:', '', result)
                result = re.sub(r'Assistant:', '', result)
                
                cleaned_result = result.strip()
                
                if cleaned_result:
                    print(f"[LLM] ✅ Cevap: {cleaned_result[:80]}...")
                    return cleaned_result
                else:
                    return "Cevap üretilemedi."
            
            elif response.status_code == 404:
                return f"❌ 404 Hatası: Model '{OLLAMA_MODEL}' bulunamadı!\n\nÇözüm:\n1. 'ollama list' komutunu çalıştır\n2. Model adını kontrol et\n3. llm.py'de OLLAMA_MODEL değişkenini düzelt"
            
            else:
                error_text = response.text
                print(f"[LLM] ❌ HTTP {response.status_code}: {error_text}")
                return f"Ollama HTTP {response.status_code}: {error_text}"

    except httpx.TimeoutException:
        print(f"[LLM] ⏱️ Timeout hatası")
        return "⏱️ Timeout - Model çok yavaş yanıt veriyor."
    except Exception as e:
        print(f"[LLM] ❌ Beklenmeyen hata: {str(e)}")
        return f"❌ Hata: {str(e)}"