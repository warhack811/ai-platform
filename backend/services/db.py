import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import OrderedDict

import chromadb
from sentence_transformers import SentenceTransformer

from services.knowledge import stats

DB_PATH = "D:/AI/backend/chroma_db"
MAX_CACHE_SIZE = 100

os.makedirs(DB_PATH, exist_ok=True)

print("=" * 60)
print("🔄 Embedding model yükleniyor...")
print("=" * 60)

try:
    embedding_model = SentenceTransformer(
        'paraphrase-multilingual-MiniLM-L12-v2',
        device='cpu'
    )
    print("✅ Embedding model hazır\n")
except Exception as e:
    print(f"❌ Embedding HATASI: {e}")
    raise

try:
    chroma_client = chromadb.PersistentClient(path=DB_PATH)
    collection = chroma_client.get_or_create_collection(
        name="knowledge_base",
        metadata={"hnsw:space": "cosine"}
    )
    print(f"✅ ChromaDB hazır. Kayıt: {collection.count()}\n")
except Exception as e:
    print(f"❌ ChromaDB HATASI: {e}")
    raise

# Basit LRU cache
search_cache = OrderedDict()


def create_embedding(text: str) -> List[float]:
    """Metin için embedding oluştur"""
    try:
        return embedding_model.encode(text, show_progress_bar=False).tolist()
    except Exception as e:
        print(f"[EMBEDDING ERROR] {e}")
        return []


def save_to_db(text: str, metadata: Dict, doc_id: str) -> bool:
    """ChromaDB'ye kayıt - web_search.py tarafından kullanılıyor"""
    try:
        # Duplicate check
        try:
            existing = collection.get(ids=[doc_id])
            if existing and existing.get('ids'):
                print(f"[DB] ⚠️  {doc_id} zaten var")
                return False
        except Exception:
            pass

        embedding = create_embedding(text)
        if not embedding:
            return False

        collection.add(
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata],
            ids=[doc_id]
        )

        stats["db_size"] = collection.count()
        print(f"[DB] ✅ {doc_id} kaydedildi (Toplam: {stats['db_size']})")
        return True

    except Exception as e:
        print(f"[DB ERROR] {e}")
        return False


def search_db(query: str, n: int = 3, min_relevance: float = 50.0) -> List[Dict]:
    """ChromaDB semantic search - main.py tarafından kullanılıyor"""
    try:
        if collection.count() == 0:
            return []

        query_embedding = create_embedding(query)
        if not query_embedding:
            return []

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n, collection.count()),
            include=['documents', 'metadatas', 'distances']
        )

        docs = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                distance = results['distances'][0][i]
                relevance = round((1 - distance) * 100, 1)

                if relevance >= min_relevance:
                    docs.append({
                        "content": doc,
                        "metadata": results['metadatas'][0][i],
                        "relevance": relevance
                    })

            docs.sort(key=lambda x: x['relevance'], reverse=True)
            if docs:
                print(f"[DB] ✅ {len(docs)} kayıt (en iyi: {docs[0]['relevance']}%)")

        return docs

    except Exception as e:
        print(f"[DB SEARCH ERROR] {e}")
        return []


def manage_cache(key: str, value: Any = None) -> Optional[Any]:
    """Thread-safe LRU cache - web_search.py tarafından kullanılıyor"""
    global search_cache

    if value is None:
        # Get
        if key in search_cache:
            search_cache.move_to_end(key)
            cached_time, cached_value = search_cache[key]
            if datetime.now() - cached_time < timedelta(hours=1):
                stats["cache_hits"] += 1
                return cached_value
            else:
                del search_cache[key]
        stats["cache_misses"] += 1
        return None
    else:
        # Set
        search_cache[key] = (datetime.now(), value)
        if len(search_cache) > MAX_CACHE_SIZE:
            search_cache.popitem(last=False)
        return value