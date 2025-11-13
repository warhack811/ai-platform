from typing import List, Dict, Optional
from datetime import datetime
from pydantic import BaseModel
import hashlib

# ============================================
# GÜVENİLİR KAYNAK LİSTESİ
# ============================================

TRUSTED_DOMAINS = {
    'official': ['.gov.tr', '.edu.tr', '.k12.tr', '.tbb.org.tr', '.tbmm.gov.tr'],
    'news': ['ntv.com.tr', 'haberturk.com', 'hurriyet.com.tr', 'milliyet.com.tr',
             'cnnturk.com', 'aa.com.tr', 'trthaber.com', 'bloomberght.com',
             'bbc.com/turkce', 'dw.com/tr', 'euronews.com/tr'],
    'tech': ['webrazzi.com', 'shiftdelete.net', 'technopat.net', 'chip.com.tr',
             'donanimhaber.com', 'logic.com.tr'],
    'health': ['saglik.gov.tr', 'medicalpark.com.tr', 'acibadem.com.tr', 'memorial.com.tr'],
    'sports': ['ntvspor.net', 'aspor.com.tr', 'fanatik.com.tr', 'tff.org',
               'transfermarkt.com.tr', 'beinsports.com.tr', 'eurosport.com.tr']
}

# ============================================
# GLOBAL İSTATİSTİKLER
# ============================================

stats = {
    "total_queries": 0,
    "total_web_searches": 0,
    "total_scraped": 0,
    "db_size": 0,
    "total_documents": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "confidence_scores": [],
    "conflicts_resolved": 0,
    "quality_rejected": 0,
    "cross_verified": 0
}

# ============================================
# MODELLER
# ============================================

class InformationSnippet(BaseModel):
    content: str
    source_type: str               # "internal_kb", "general_web", "official_site" vs.
    source_url: Optional[str] = None
    confidence: float = 0.5
    timestamp: datetime = datetime.now()
    freshness: float = 1.0
    category: Optional[str] = None
    quality_score: float = 0.5
    domain_trust: float = 0.5


class CoreKnowledge(BaseModel):
    fact: str
    category: str
    last_verified: datetime
    confidence: float = 0.8


# ============================================
# GELİŞMİŞ BİLGİ SİSTEMİ
# ============================================

class AdvancedKnowledgeSystem:
    """
    Web + DB + temel bilgi + kalite kontrol + çapraz doğrulama
    hepsini birleştiren katman.
    """

    def __init__(self):
        self.core_knowledge_db: Dict[str, CoreKnowledge] = {}
        self.source_weights = {
            'official_site': 0.95,
            'reputable_news': 0.90,
            'general_web': 0.75,
            'user_uploaded': 0.70,
            'internal_kb': 0.85,
            'core_knowledge': 0.80,
            'unknown': 0.50
        }
        self.load_core_knowledge()

    def load_core_knowledge(self):
        base_knowledge = [
            {"fact": "Türkiye'nin başkenti Ankara'dır", "category": "coğrafya", "confidence": 0.95},
            {"fact": "İstanbul Türkiye'nin en kalabalık şehridir", "category": "coğrafya", "confidence": 0.90},
            {"fact": "Python popüler bir programlama dilidir", "category": "teknoloji", "confidence": 0.85},
            {"fact": "Yapay zeka makine öğrenimi ve derin öğrenme tekniklerini kullanır",
             "category": "teknoloji", "confidence": 0.80},
        ]

        for knowledge in base_knowledge:
            key = hashlib.md5(knowledge["fact"].encode()).hexdigest()
            self.core_knowledge_db[key] = CoreKnowledge(
                fact=knowledge["fact"],
                category=knowledge["category"],
                last_verified=datetime.now(),
                confidence=knowledge["confidence"]
            )

    # -----------------------------
    # DOMAIN GÜVENİ + KALİTE ANALİZİ
    # -----------------------------

    def get_domain_trust_score(self, url: str) -> float:
        if not url:
            return 0.5

        url_lower = url.lower()

        for domain in TRUSTED_DOMAINS['official']:
            if domain in url_lower:
                return 0.95

        for domain in TRUSTED_DOMAINS['news']:
            if domain in url_lower:
                return 0.85

        for category in ['tech', 'health', 'sports']:
            for domain in TRUSTED_DOMAINS[category]:
                if domain in url_lower:
                    return 0.80

        spam_domains = ['click.com', 'spam.com', 'fake.com']
        if any(domain in url_lower for domain in spam_domains):
            return 0.1

        return 0.5

    def assess_content_quality_advanced(self, content: str, title: str = "", url: str = "") -> Dict:
        """
        İçerik uzunluğu + çeşitliliği + formatı + domain güveni bazlı gelişmiş kalite skoru.
        """
        score = 0.5

        content_length = len(content)
        if content_length > 500:
            score += 0.3
        elif content_length > 200:
            score += 0.2
        elif content_length > 100:
            score += 0.1
        elif content_length < 50:
            score -= 0.3
        elif content_length < 20:
            score -= 0.5

        sentence_count = content.count('.') + content.count('!') + content.count('?')
        if sentence_count > 3:
            score += 0.2

        paragraph_count = content.count('\n\n')
        if paragraph_count > 1:
            score += 0.1

        words = content.split()
        if len(words) > 10:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.4:
                score -= 0.3
            elif unique_ratio > 0.8:
                score += 0.1

        if any(marker in content for marker in ['•', '- ', '1.', '2.', '3.']):
            score += 0.1

        domain_score = self.get_domain_trust_score(url)
        score += domain_score * 0.2

        if title and content:
            title_words = set(title.lower().split()[:5])
            content_start = set(content.lower().split()[:20])
            if title_words.intersection(content_start):
                score += 0.1

        return {
            "quality_score": max(0.1, min(1.0, score)),
            "domain_trust": domain_score,
            "content_length": content_length,
            "sentence_count": sentence_count
        }

    # -----------------------------
    # ANAHTAR İFADE ÇIKARMA
    # -----------------------------

    def extract_key_phrases(self, text: str) -> List[str]:
        words = text.lower().split()
        stop_words = ['nedir', 'nasıl', 'nerede', 'ne', 'bir', 've', 'ile', 'için']
        key_words = [word for word in words if word not in stop_words and len(word) > 2]

        bigrams = []
        for i in range(len(key_words) - 1):
            bigrams.append(f"{key_words[i]} {key_words[i + 1]}")

        return bigrams + key_words

    # -----------------------------
    # ÇAPRAZ DOĞRULAMA
    # -----------------------------

    def cross_verify_information(self, snippets: List[InformationSnippet], query: str) -> Dict:
        if len(snippets) < 2:
            return {"verified": False, "consensus": 0.0, "conflicting_sources": []}

        key_phrases = self.extract_key_phrases(query)
        verification_results = []

        for phrase in key_phrases[:3]:
            phrase_lower = phrase.lower()
            supporting_sources = []
            conflicting_sources = []

            for snippet in snippets:
                content_lower = snippet.content.lower()
                if phrase_lower in content_lower:
                    supporting_sources.append({
                        "source": snippet.source_url,
                        "confidence": snippet.confidence,
                        "content_preview": snippet.content[:100]
                    })
                else:
                    negative_patterns = [
                        f"değil {phrase_lower}", f"yanlış {phrase_lower}",
                        f"olmamış {phrase_lower}", f"iptal {phrase_lower}"
                    ]
                    if any(pattern in content_lower for pattern in negative_patterns):
                        conflicting_sources.append({
                            "source": snippet.source_url,
                            "confidence": snippet.confidence,
                            "content_preview": snippet.content[:100]
                        })

            verification_results.append({
                "key_phrase": phrase,
                "supporting_count": len(supporting_sources),
                "conflicting_count": len(conflicting_sources),
                "supporting_sources": supporting_sources,
                "conflicting_sources": conflicting_sources
            })

        total_verifications = len(verification_results)
        if total_verifications == 0:
            consensus = 0.0
        else:
            consensus = sum(
                1 for result in verification_results
                if result["supporting_count"] > result["conflicting_count"]
            ) / total_verifications

        stats["cross_verified"] += 1

        return {
            "verified": consensus > 0.5,
            "consensus": round(consensus, 2),
            "verification_results": verification_results,
            "total_sources": len(snippets)
        }

    # -----------------------------
    # TEMEL BİLGİYLE BİRLEŞTİRME
    # -----------------------------

    def get_relevant_core_knowledge(self, query: str) -> List[CoreKnowledge]:
        relevant: List[CoreKnowledge] = []
        query_lower = query.lower()

        for knowledge in self.core_knowledge_db.values():
            if (query_lower in knowledge.fact.lower() or
                    any(word in knowledge.fact.lower() for word in query_lower.split())):
                relevant.append(knowledge)

        return relevant[:3]

    # -----------------------------
    # ÇAKIŞMA TESPİT (ŞU AN BASİT)
    # -----------------------------

    def detect_conflicts(self, snippets: List[InformationSnippet]) -> List[Dict]:
        conflicts: List[Dict] = []
        # İleride sayısal/tarihsel çakışma analizi buraya eklenebilir
        return conflicts

    # -----------------------------
    # GENEL DEĞERLENDİRME
    # -----------------------------

    def evaluate_information_quality(
        self,
        web_snippets: List[InformationSnippet],
        db_snippets: List[InformationSnippet],
        query: str
    ) -> Dict:
        all_snippets: List[InformationSnippet] = web_snippets + db_snippets
        core_knowledge = self.get_relevant_core_knowledge(query)

        for knowledge in core_knowledge:
            core_snippet = InformationSnippet(
                content=knowledge.fact,
                source_type="core_knowledge",
                confidence=knowledge.confidence,
                timestamp=knowledge.last_verified,
                freshness=1.0,
                category=knowledge.category
            )
            all_snippets.append(core_snippet)

        for snippet in all_snippets:
            hours_ago = (datetime.now() - snippet.timestamp).total_seconds() / 3600
            snippet.freshness = max(0.3, 1.0 - (hours_ago / (30 * 24)))

            quality_assessment = self.assess_content_quality_advanced(
                snippet.content,
                snippet.source_url or "",
                snippet.source_url or ""
            )
            snippet.quality_score = quality_assessment["quality_score"]
            snippet.domain_trust = quality_assessment["domain_trust"]

            source_weight = self.source_weights.get(snippet.source_type, 0.5)

            snippet.confidence = round(
                source_weight * snippet.freshness * snippet.quality_score * snippet.domain_trust,
                2
            )

        cross_verification = self.cross_verify_information(all_snippets, query)
        conflicts = self.detect_conflicts(all_snippets)

        sorted_snippets = sorted(all_snippets, key=lambda x: x.confidence, reverse=True)

        return {
            "snippets": sorted_snippets,
            "has_conflicts": len(conflicts) > 0,
            "conflicts": conflicts,
            "highest_confidence": sorted_snippets[0].confidence if sorted_snippets else 0.0,
            "core_knowledge_used": len(core_knowledge),
            "cross_verification": cross_verification
        }


# Global bilgi sistemi instance'ı
knowledge_system = AdvancedKnowledgeSystem()
