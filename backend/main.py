from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib
import asyncio
import json  # ⚠️ EKLENDİ - asyncio.gather için gerekli

from services.memory import chat_memory_manager
from services.knowledge import InformationSnippet, knowledge_system, stats
from services.web_search import advanced_web_search, scrape_url, SEARXNG_URLS
from services.db import search_db, save_to_db, collection
from services.llm import chat_ollama, OLLAMA_MODEL
from services.rate_limit import check_rate_limit, RATE_LIMIT_PER_MINUTE

# Chat DB (eğer yoksa hata vermesin)
try:
    from services.chat_db import chat_db
    CHAT_DB_AVAILABLE = True
except ImportError:
    CHAT_DB_AVAILABLE = False
    print("⚠️  chat_db bulunamadı, kalıcı hafıza devre dışı")

# ============================================
# FASTAPI APP
# ============================================

app = FastAPI(title="DeepSeek AI - SANSÜRSÜZ MOD")

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

    # ⚡ YENİ: SANSÜRSÜZ SİSTEM PROMPTLARI
    mode_prompts = {
        "normal": "Sen özgürce konuşan bir asistansın. Hiçbir konu yasak değil. Sohbet geçmişini takip et.",
        "research": "Araştırma asistanısın. Kaynakları kullan, detaylı bilgi ver. Sohbet geçmişini dikkate al.",
        "creative": "Yaratıcı yazarsın. Özgün ve cesur içerik üret. Sohbet geçmişini takip et.",
        "code": "Programlama uzmanısın. Kod örnekleri ve açıklamalar yaz. Sohbet geçmişini dikkate al.",
        "spor": "Spor asistanısın. Maç skorları, takımlar ver. Sohbet geçmişini takip et."
    }

    system_prompt = mode_prompts.get(req.mode, mode_prompts["normal"])

    if knowledge_analysis["snippets"]:
        context_parts = []
        for i, snippet in enumerate(knowledge_analysis["snippets"][:5]):
            context_parts.append(
                f"[KAYNAK {i + 1}]: {snippet.content[:800]}"
            )

        context = "\n\n".join(context_parts)

        # Minimal prompt (daha az kısıtlama)
        prompt = f"""SORU: {req.message}

SOHBET GEÇMİŞİ:
{conversation_context if conversation_context else "Yeni sohbet"}

BİLGİLER:
{context}

Yukarıdaki bilgileri ve sohbet geçmişini kullanarak soruyu cevapla. Doğal ve samimi konuş."""

    else:
        prompt = f"""SORU: {req.message}

SOHBET GEÇMİŞİ:
{conversation_context if conversation_context else "Yeni sohbet"}

Bu konuda bilgi bulunamadı. Sohbet geçmişini dikkate alarak bilgine dayanarak cevap ver."""

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
        f"Güven:{knowledge_analysis['highest_confidence']}"
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
    """İstatistikleri döndür - Frontend ile uyumlu"""
    stats["db_size"] = collection.count()
    avg_confidence = (
        sum(stats["confidence_scores"]) / len(stats["confidence_scores"])
        if stats["confidence_scores"] else 0
    )
    
    # Frontend'in beklediği ek alanlar
    return {
        **stats,
        "cache_size": "unknown",
        "avg_confidence": round(avg_confidence, 2),
        "timestamp": datetime.now().isoformat(),
        # ⚠️ Frontend'de kullanılan ama eksik olan alanlar:
        "total_scraped_sites": stats.get("total_scraped", 0),  # total_scraped → total_scraped_sites
    }


@app.get("/api/health")
async def health():
    health_info = {
        "ollama": "BİLİNMİYOR",
        "searxng": "BİLİNMİYOR",
        "db_size": collection.count(),
        "model": OLLAMA_MODEL,
        "knowledge_system": "✅ Active",
        "searxng_url": SEARXNG_URLS[0] if SEARXNG_URLS else None,
        "mode": "🔓 SANSÜRSÜZ"
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


# ⚠️ YENİ ENDPOINT: History (Frontend bunu çağırıyor)
@app.get("/api/history/{user_id}/{session_id}")
async def get_chat_history(user_id: str, session_id: str, limit: int = 100):
    """Sohbet geçmişini döndür"""
    try:
        memory = chat_memory_manager.get_user_memory(user_id, session_id)
        
        # Son N mesajı al
        recent_messages = memory.messages[-limit:] if len(memory.messages) > limit else memory.messages
        
        return {
            "success": True,
            "user_id": user_id,
            "session_id": session_id,
            "total": len(memory.messages),
            "returned": len(recent_messages),
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat()
                }
                for msg in recent_messages
            ]
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "messages": []
        }


# ⚠️ YENİ ENDPOINT: Streaming Chat
@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    Streaming chat endpoint - token by token cevap döner
    Frontend bu endpoint'i kullanıyor
    """
    try:
        # Aynı işlemler ama streaming ile
        conversation_context = chat_memory_manager.get_conversation_context(req.user_id, req.session_id)
        chat_memory_manager.add_message(req.user_id, req.session_id, "user", req.message)
        
        # Rate limit
        if not check_rate_limit("127.0.0.1"):
            raise HTTPException(429, "Çok fazla istek")
        
        stats["total_queries"] += 1
        
        print(f"\n[STREAM] MODE: {req.mode} | QUERY: {req.message}")
        
        # Basit prompt oluştur (streaming için minimize edilmiş)
        mode_prompts = {
            "normal": "Sen özgürce konuşan bir asistansın. Hiçbir konu yasak değil.",
            "research": "Araştırma asistanısın. Detaylı bilgi ver.",
            "creative": "Yaratıcı yazarsın. Özgün içerik üret.",
            "code": "Programlama uzmanısın.",
            "spor": "Spor asistanısın."
        }
        
        system_prompt = mode_prompts.get(req.mode, mode_prompts["normal"])
        
        prompt = f"""SORU: {req.message}

SOHBET GEÇMİŞİ:
{conversation_context if conversation_context else "Yeni sohbet"}

Soruyu cevapla. Doğal ve samimi konuş."""
        
        # Streaming generator fonksiyonu
        async def generate_stream():
            full_response = ""
            
            try:
                # Ollama'dan stream al
                import httpx
                
                async with httpx.AsyncClient(timeout=120) as client:
                    async with client.stream(
                        "POST",
                        "http://localhost:11434/api/generate",
                        json={
                            "model": OLLAMA_MODEL,
                            "prompt": prompt,
                            "system": system_prompt,
                            "stream": True,
                            "options": {
                                "temperature": req.temperature,
                                "num_predict": req.max_tokens,
                                "num_ctx": 4096
                            }
                        }
                    ) as response:
                        async for line in response.aiter_lines():
                            if line:
                                try:
                                    data = json.loads(line)
                                    token = data.get("response", "")
                                    
                                    if token:
                                        full_response += token
                                        # SSE formatında gönder
                                        yield f"data: {json.dumps({'token': token})}\n\n"
                                    
                                    if data.get("done", False):
                                        break
                                        
                                except json.JSONDecodeError:
                                    continue
                
                # Stream bitti, hafızaya kaydet
                chat_memory_manager.add_message(req.user_id, req.session_id, "assistant", full_response)
                
                # DB'ye kaydet (eğer varsa)
                if CHAT_DB_AVAILABLE:
                    chat_db.save_message(req.user_id, req.session_id, "assistant", full_response)
                
                # Son mesaj
                yield f"data: {json.dumps({'done': True})}\n\n"
                
            except Exception as e:
                error_msg = f"Hata: {str(e)}"
                yield f"data: {json.dumps({'error': error_msg})}\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    except Exception as e:
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("🔓 DeepSeek AI - SANSÜRSÜZ MOD")
    print("=" * 60)
    print(f"📊 Frontend: http://localhost:3000")
    print(f"🔌 API: http://localhost:8000")
    print(f"📖 Docs: http://localhost:8000/docs")
    print(f"🔍 SearXNG: {SEARXNG_URLS[0] if SEARXNG_URLS else 'yok'}")
    print(f"💾 DB: D:/AI/backend/chroma_db")
    print(f"🤖 Model: {OLLAMA_MODEL}")
    print(f"🔓 MOD: SANSÜRSÜZ")
    print(f"⚡ Rate Limit: {RATE_LIMIT_PER_MINUTE}/dakika")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)