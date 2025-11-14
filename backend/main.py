from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse  # ← YENİ
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib
import asyncio  # ← YENİ (eğer yoksa)
import json  # ← YENİ

from services.memory import chat_memory_manager
from services.knowledge import InformationSnippet, knowledge_system, stats
from services.web_search import advanced_web_search, scrape_url, SEARXNG_URLS
from services.db import search_db, save_to_db, collection
from services.llm import chat_ollama, chat_ollama_stream  # ← YENİ: stream ekledik
from services.llm import chat_ollama, OLLAMA_MODEL
from services.rate_limit import check_rate_limit, RATE_LIMIT_PER_MINUTE
from services.chat_db import chat_db  # ← YENİ: SQLite DB

# ============================================
# FASTAPI APP
# ============================================

app = FastAPI(title="DeepSeek AI - GELİŞMİŞ BİLGİ SİSTEMİ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# MODELLER
# ============================================

class ChatRequest(BaseModel):
    message: str
    mode: str = "normal"
    use_web_search: bool = True
    max_sources: int = 5
    temperature: float = 0.3
    max_tokens: int = 800
    user_id: str = "default"
    session_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    sources: List[Dict] = []
    used_db: bool = False
    used_web: bool = False
    db_count: int = 0
    web_count: int = 0
    mode: str = "normal"
    confidence_score: float = 0.0
    has_conflicts: bool = False
    conflicts: List[Dict] = []
    knowledge_used: List[str] = []
    cross_verification: Dict[str, Any] = {}

class DocumentUpload(BaseModel):
    content: str
    filename: str


# ============================================
# YARDIMCI FONKSİYONLAR
# ============================================

def looks_followup(text: str) -> bool:
    t = text.strip().lower()
    triggers = ["yarın", "peki", "devam", "sonra", "o", "bu", "yarın nasıl", "hangisi"]
    return any(x in t for x in triggers) or len(t.split()) < 3


# ============================================
# DEBUG: HAFIZA GÖRME
# ============================================

@app.get("/api/debug/memory/{user_id}/{session_id}")
async def debug_memory(user_id: str, session_id: str):
    memory = chat_memory_manager.get_user_memory(user_id, session_id)
    conversation_context = chat_memory_manager.get_conversation_context(user_id, session_id)

    return {
        "user_id": user_id,
        "session_id": session_id,
        "total_messages": len(memory.messages),
        "last_activity": memory.last_activity.isoformat(),
        "conversation_context_preview": conversation_context[-500:] if conversation_context else "Boş",
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat()
            }
            for msg in memory.messages
        ]
    }

# ============================================
# ANA CHAT ENDPOINT
# ============================================

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, x_forwarded_for: Optional[str] = Header(None)):
    # 1) Sohbet hafızası
    conversation_context = chat_memory_manager.get_conversation_context(req.user_id, req.session_id)
    chat_memory_manager.add_message(req.user_id, req.session_id, "user", req.message)

    # 2) Rate limit
    client_ip = x_forwarded_for or "127.0.0.1"
    if not check_rate_limit(client_ip):
        raise HTTPException(429, "Çok fazla istek. Dakikada max 30 sorgu.")

    stats["total_queries"] += 1

    print(f"\n{'=' * 60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] MODE: {req.mode} | QUERY: {req.message}")
    print(f"💬 Sohbet Geçmişi: {len(conversation_context.splitlines())} satır")
    print(f"{'=' * 60}")

    sources: List[Dict] = []
    web_snippets: List[InformationSnippet] = []
    db_snippets: List[InformationSnippet] = []
    used_db = False
    used_web = False

    # 3) DB araması
    print("[1/5] ChromaDB aranıyor...")
    db_results = search_db(req.message, n=3, min_relevance=60.0)

    if db_results:
        used_db = True
        for item in db_results:
            scraped_at = item["metadata"].get("scraped_at", datetime.now().isoformat())
            db_snippets.append(
                InformationSnippet(
                    content=item["content"],
                    source_type="internal_kb",
                    source_url=item["metadata"].get("url", ""),
                    confidence=item["relevance"] / 100,
                    timestamp=datetime.fromisoformat(scraped_at),
                    category=item["metadata"].get("category", "general")
                )
            )

    # 4) Web araması
    if req.use_web_search:
        print("[2/5] Gelişmiş web araması yapılıyor...")
        stats["total_web_searches"] += 1

        mem = chat_memory_manager.get_user_memory(req.user_id, req.session_id)
        last_user_msgs = [m.content for m in mem.messages if m.role == "user"][-8:]

        augmented_query = req.message
        if looks_followup(req.message) and last_user_msgs:
            ctx_text = " ".join(last_user_msgs[:-1] or last_user_msgs)
            augmented_query = f"{ctx_text} {req.message}"
            print(f"[CTX] Takip sorusu tespit edildi -> {augmented_query}")

        search_results = await advanced_web_search(augmented_query, req.max_sources)

        if search_results:
            used_web = True
            print(f"[3/5] {len(search_results)} URL scraping...")

            scrape_tasks = [scrape_url(r["url"]) for r in search_results]
            scraped_contents = await asyncio.gather(*scrape_tasks, return_exceptions=True)

            for result, content in zip(search_results, scraped_contents):
                if isinstance(content, str) and len(content) > 100:
                    qa = knowledge_system.assess_content_quality_advanced(
                        content, result["title"], result["url"]
                    )
                    if qa["quality_score"] < 0.4:
                        stats["quality_rejected"] += 1
                        continue

                    domain_trust = qa["domain_trust"]
                    source_type = "general_web"
                    if domain_trust > 0.9:
                        source_type = "official_site"
                    elif domain_trust > 0.8:
                        source_type = "reputable_news"

                    doc_id = f"web_{hashlib.md5(result['url'].encode()).hexdigest()[:8]}"
                    if save_to_db(content, {
                        "source": "web",
                        "url": result["url"],
                        "title": result["title"],
                        "query": req.message,
                        "category": "web_scraped",
                        "scraped_at": datetime.now().isoformat(),
                        "quality_score": qa["quality_score"],
                        "domain_trust": domain_trust
                    }, doc_id):
                        stats["total_scraped"] += 1

                    web_snippets.append(
                        InformationSnippet(
                            content=f"{result['title']}: {content}",
                            source_type=source_type,
                            source_url=result["url"],
                            confidence=domain_trust * 0.8,
                            timestamp=datetime.now(),
                            category="web_content",
                            quality_score=qa["quality_score"],
                            domain_trust=domain_trust
                        )
                    )
                    sources.append({
                        "title": result["title"],
                        "url": result["url"],
                        "quality_score": round(qa["quality_score"], 2),
                        "domain_trust": round(domain_trust, 2)
                    })

            print(f"[3/5] ✅ {len(sources)} kaliteli kaynak")

    # 5) Bilgi değerlendirme
    print("[4/5] Gelişmiş bilgi değerlendirmesi yapılıyor...")
    knowledge_analysis = knowledge_system.evaluate_information_quality(
        web_snippets, db_snippets, req.message
    )

    # 6) Prompt & model
    print("[5/5] Cevap oluşturuluyor...")

    # MODE BAZLI KİŞİLİK SİSTEMİ
    # MODE BAZLI KİŞİLİK SİSTEMİ
    mode_prompts = {
    "normal": """Sen akıllı, yardımsever bir yapay zeka asistanısın. 
KURALLAR:
- Doğal Türkçe konuş (robot gibi değil)
- Verilen bilgileri kullan, eğer yoksa genel bilgini kullan
- Kısa ve net cevaplar ver
- Gereksiz tekrar yapma""",

    "research": """Sen profesyonel araştırma asistanısın.
KURALLAR:
- Akademik ve detaylı cevaplar ver
- Kaynakları referans göster
- Bilimsel yöntemle yaklaş
- Tartışmalı konularda tarafsız kal
- Verilen kaynaklardaki bilgileri önceliklendir""",

    "creative": """Sen yaratıcı bir yazarsın.
KURALLAR:
- Akıcı ve duygusal dil kullan
- Metaforlar, örnekler ekle
- Hayal gücünü kullan
- Verilen bilgileri yaratıcı şekilde işle""",

    "code": """Sen deneyimli bir yazılım mühendisisin.
KURALLAR:
- Kod örnekleri ver
- Best practices kullan
- Açıklayıcı yorumlar ekle
- Alternatif çözümler sun
- Temiz ve okunabilir kod yaz""",

    "friend": """Sen samimi bir arkadaşsın.
KURALLAR:
- Doğal, günlük dil kullan
- Empati kur
- Sohbet havasında cevapla
- Resmi olmayan üslup kullan""",

    "assistant": """Sen kişisel asistansın.
KURALLAR:
- Organize ve verimli ol
- Pratik çözümler sun
- Adım adım rehberlik et
- Net ve actionable öneriler ver"""
}

    system_prompt = mode_prompts.get(req.mode, mode_prompts["normal"])

    if knowledge_analysis["snippets"]:
        context_parts = []
        for i, snippet in enumerate(knowledge_analysis["snippets"][:5]):
            # Kaynak türüne göre etiket
            if snippet.source_type == "internal_kb":
                source_label = "💾 VERİTABANI"
            elif snippet.source_type == "official_site":
                source_label = "🏛️ RESMİ"
            elif snippet.source_type == "reputable_news":
                source_label = "📰 HABER"
            else:
                source_label = "🌐 WEB"

            context_parts.append(
                f"{source_label} {i+1} (Güven: {int(snippet.confidence*100)}%):\n{snippet.content[:800]}"
            )

        context = "\n\n".join(context_parts)

        # Doğrulama bilgisi
        if knowledge_analysis["cross_verification"]["verified"]:
            verify_info = f"✅ {len(knowledge_analysis['snippets'])} kaynak doğrulandı"
        else:
            verify_info = "⚠️ Tek kaynak"

        # Çatışma bilgisi
        conflict_info = ""
        if knowledge_analysis["has_conflicts"]:
            conflict_info = "\n🚨 Bilgi çatışması var"

        # PROMPT
        prompt = f"""SEN: {system_prompt}

📅 {datetime.now().strftime('%d %B %Y')}

💬 SOHBET:
{conversation_context if conversation_context else "[İlk mesaj]"}

❓ SORU: {req.message}

📚 BİLGİLER:
{context}

{verify_info}
{conflict_info}

🎯 Doğal Türkçe ile cevapla:"""

    else:
        # Bilgi bulunamadı
        prompt = f"""SEN: {system_prompt}

📅 {datetime.now().strftime('%d %B %Y')}

💬 SOHBET:
{conversation_context if conversation_context else "[İlk mesaj]"}

❓ SORU: {req.message}

⚠️ Güncel bilgi yok

🎯 Genel bilginle doğal cevap ver:"""

    response_text = await chat_ollama(
        prompt,
        system_prompt,
        req.temperature,
        req.max_tokens
    )

    chat_memory_manager.add_message(req.user_id, req.session_id, "assistant", response_text)

    stats["confidence_scores"].append(knowledge_analysis["highest_confidence"])
    if len(stats["confidence_scores"]) > 100:
        stats["confidence_scores"] = stats["confidence_scores"][-100:]

    print(
        f"[DONE] DB:{used_db} Web:{used_web} "
        f"Güven:{knowledge_analysis['highest_confidence']} "
        f"Çapraz:{knowledge_analysis['cross_verification']['consensus']}"
    )
    print("=" * 60 + "\n")

    return ChatResponse(
        response=response_text,
        sources=sources,
        used_db=used_db,
        used_web=used_web,
        db_count=len(db_snippets),
        web_count=len(sources),
        mode=req.mode,
        confidence_score=knowledge_analysis["highest_confidence"],
        has_conflicts=knowledge_analysis["has_conflicts"],
        conflicts=knowledge_analysis["conflicts"],
        knowledge_used=[s.source_type for s in knowledge_analysis["snippets"][:3]],
        cross_verification=knowledge_analysis["cross_verification"]
    )


# ============================================
# STREAMING CHAT ENDPOINT (YENİ)
# ============================================

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, x_forwarded_for: Optional[str] = Header(None)):
    """Streaming chat endpoint - kelime kelime cevap"""
    
    # Rate limit
    client_ip = x_forwarded_for or "127.0.0.1"
    if not check_rate_limit(client_ip):
        raise HTTPException(429, "Çok fazla istek.")
    
    # Kullanıcı mesajını kaydet
    chat_memory_manager.add_message(req.user_id, req.session_id, "user", req.message)
    chat_db.save_message(req.user_id, req.session_id, "user", req.message)
    
    async def generate():
        """Generator fonksiyon - streaming için"""
        try:
            # 1) Sohbet hafızası
            conversation_context = chat_memory_manager.get_conversation_context(
                req.user_id, req.session_id
            )
            
            # 2) Web araması (aynı mantık)
            sources = []
            web_snippets = []
            db_snippets = []
            
            # DB araması
            db_results = search_db(req.message, n=3, min_relevance=60.0)
            if db_results:
                for item in db_results:
                    scraped_at = item["metadata"].get("scraped_at", datetime.now().isoformat())
                    db_snippets.append(
                        InformationSnippet(
                            content=item["content"],
                            source_type="internal_kb",
                            source_url=item["metadata"].get("url", ""),
                            confidence=item["relevance"] / 100,
                            timestamp=datetime.fromisoformat(scraped_at),
                            category=item["metadata"].get("category", "general")
                        )
                    )
            
            # Web araması (basitleştirilmiş)
            if req.use_web_search:
                search_results = await advanced_web_search(req.message, req.max_sources)
                if search_results:
                    scrape_tasks = [scrape_url(r["url"]) for r in search_results]
                    scraped_contents = await asyncio.gather(*scrape_tasks, return_exceptions=True)
                    
                    for result, content in zip(search_results, scraped_contents):
                        if isinstance(content, str) and len(content) > 100:
                            qa = knowledge_system.assess_content_quality_advanced(
                                content, result["title"], result["url"]
                            )
                            if qa["quality_score"] >= 0.4:
                                domain_trust = qa["domain_trust"]
                                web_snippets.append(
                                    InformationSnippet(
                                        content=f"{result['title']}: {content}",
                                        source_type="general_web",
                                        source_url=result["url"],
                                        confidence=domain_trust * 0.8,
                                        timestamp=datetime.now(),
                                        category="web_content",
                                        quality_score=qa["quality_score"],
                                        domain_trust=domain_trust
                                    )
                                )
                                sources.append({
                                    "title": result["title"],
                                    "url": result["url"]
                                })
            
            # 3) Bilgi analizi
            knowledge_analysis = knowledge_system.evaluate_information_quality(
                web_snippets, db_snippets, req.message
            )
            
            # 4) Prompt oluştur (aynı mantık)
            mode_prompts = {
                "normal": "Sen yardımcı bir AI asistanısın. Sohbet geçmişini dikkate al.",
                "research": "Sen araştırma asistanısın. Detaylı bilgi ver.",
                "creative": "Sen yaratıcı yazarsın.",
                "code": "Sen programlama uzmanısın."
            }
            system_prompt = mode_prompts.get(req.mode, mode_prompts["normal"])
            
            if knowledge_analysis["snippets"]:
                context_parts = []
                for i, snippet in enumerate(knowledge_analysis["snippets"][:5]):
                    context_parts.append(
                        f"[KAYNAK {i+1}]: {snippet.content[:800]}"
                    )
                context = "\n\n".join(context_parts)
                
                prompt = f"""KULLANICI SORUSU: {req.message}

💬 SOHBET GEÇMİŞİ:
{conversation_context if conversation_context else "Yeni sohbet"}

BULUNAN BİLGİLER:
{context}

CEVAP (Türkçe):"""
            else:
                prompt = f"""KULLANICI SORUSU: {req.message}

💬 SOHBET GEÇMİŞİ:
{conversation_context if conversation_context else "Yeni sohbet"}

CEVAP (Türkçe):"""
            
            # 5) İlk olarak metadata gönder (kaynaklar)
            metadata = {
                "type": "metadata",
                "sources": sources,
                "db_count": len(db_snippets),
                "web_count": len(sources)
            }
            yield f"data: {json.dumps(metadata, ensure_ascii=False)}\n\n"
            
            # 6) Streaming cevap
            full_response = ""
            async for chunk in chat_ollama_stream(
                prompt, system_prompt, req.temperature, req.max_tokens
            ):
                full_response += chunk
                data = {"type": "chunk", "content": chunk}
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            
            # 7) Cevabı kaydet
            chat_memory_manager.add_message(req.user_id, req.session_id, "assistant", full_response)
            chat_db.save_message(req.user_id, req.session_id, "assistant", full_response, {
                "sources": sources,
                "mode": req.mode
            })
            
            # 8) Bitti sinyali
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except Exception as e:
            error_data = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
# ============================================
# DİĞER ENDPOINT'LER
# ============================================

@app.post("/api/upload-document")
async def upload_doc(doc: DocumentUpload):
    try:
        if len(doc.content) < 50:
            raise HTTPException(400, "İçerik çok kısa")

        doc_id = f"doc_{datetime.now().timestamp()}"

        if save_to_db(doc.content, {
            "source": "user_upload",
            "filename": doc.filename,
            "uploaded_at": datetime.now().isoformat(),
            "category": "user_content"
        }, doc_id):
            stats["total_documents"] += 1
            return {"success": True, "message": f"✅ {doc.filename}"}
        else:
            return {"success": False, "message": "Kayıt sırasında hata oluştu"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/stats")
async def get_stats():
    stats["db_size"] = collection.count()
    avg_confidence = (
        sum(stats["confidence_scores"]) / len(stats["confidence_scores"])
        if stats["confidence_scores"] else 0
    )
    return {
        **stats,
        "cache_size": "unknown",   # cache boyutu services/db içinde tutuluyor
        "avg_confidence": round(avg_confidence, 2),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/health")
async def health():
    # Basit sağlık kontrolü
    health_info = {
        "ollama": "BİLİNMİYOR",
        "searxng": "BİLİNMİYOR",
        "db_size": collection.count(),
        "model": OLLAMA_MODEL,
        "knowledge_system": "✅ Active",
        "searxng_url": SEARXNG_URLS[0] if SEARXNG_URLS else None
    }
    return health_info


@app.get("/api/chat/memory/{user_id}/{session_id}")
async def get_chat_memory(user_id: str, session_id: str):
    memory = chat_memory_manager.get_user_memory(user_id, session_id)
    return {
        "user_id": user_id,
        "session_id": session_id,
        "total_messages": len(memory.messages),
        "last_activity": memory.last_activity,
        "messages": [
            {
                "role": msg.role,
                "content": msg.content[:200] + "..." if len(msg.content) > 200 else msg.content,
                "timestamp": msg.timestamp
            }
            for msg in memory.messages[-10:]
        ]
    }


@app.delete("/api/chat/memory/{user_id}/{session_id}")
async def clear_chat_memory(user_id: str, session_id: str):
    chat_memory_manager.clear_memory(user_id, session_id)
    return {"success": True, "message": "Sohbet hafızası temizlendi"}

# ============================================
# CHAT HISTORY ENDPOINT'LERİ (YENİ)
# ============================================

@app.get("/api/history/{user_id}/{session_id}")
async def get_history(user_id: str, session_id: str, limit: int = 50):
    """Kullanıcının chat geçmişini getir (SQLite'dan)"""
    history = chat_db.get_history(user_id, session_id, limit)
    return {"history": history, "count": len(history)}


@app.post("/api/history/export")
async def export_history(req: dict):
    """Chat geçmişini JSON olarak export et"""
    user_id = req.get("user_id")
    session_id = req.get("session_id")
    
    if not user_id or not session_id:
        raise HTTPException(400, "user_id ve session_id gerekli")
    
    json_data = chat_db.export_history(user_id, session_id)
    return StreamingResponse(
        iter([json_data]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=chat_{session_id}.json"}
    )


@app.delete("/api/history/{user_id}/{session_id}")
async def delete_history(user_id: str, session_id: str):
    """Chat geçmişini sil"""
    chat_db.clear_session(user_id, session_id)
    chat_memory_manager.clear_memory(user_id, session_id)
    return {"success": True, "message": "Geçmiş silindi"}

if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("🚀 Muhammet AI - GELİŞMİŞ BİLGİ SİSTEMİ")
    print("=" * 60)
    print(f"📊 Frontend: http://localhost:3000")
    print(f"🔌 API: http://localhost:8000")
    print(f"📖 Docs: http://localhost:8000/docs")
    print(f"🔍 SearXNG: {SEARXNG_URLS[0] if SEARXNG_URLS else 'yok'}")
    print(f"💾 DB: D:/AI/backend/chroma_db")
    print(f"🤖 Model: {OLLAMA_MODEL}")
    print(f"🧠 Gelişmiş Bilgi Sistemi: AKTİF")
    print(f"⚡ Rate Limit: {RATE_LIMIT_PER_MINUTE}/dakika")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
