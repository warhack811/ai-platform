from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from typing import List, Dict, Optional
import json

Base = declarative_base()

class ChatHistory(Base):
    __tablename__ = "chat_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user veya assistant
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.now)
    extra_data = Column(Text, default="{}")  # ← DEĞİŞTİ: metadata yerine extra_data


class ChatDatabase:
    """SQLite ile kalıcı chat hafızası"""
    
    def __init__(self, db_path: str = "D:/AI/backend/chat_history.db"):
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def save_message(
        self, 
        user_id: str, 
        session_id: str, 
        role: str, 
        content: str,
        extra_data: Optional[Dict] = None  # ← DEĞİŞTİ: metadata yerine extra_data
    ):
        """Mesajı veritabanına kaydet"""
        session = self.SessionLocal()
        try:
            msg = ChatHistory(
                user_id=user_id,
                session_id=session_id,
                role=role,
                content=content,
                extra_data=json.dumps(extra_data or {})  # ← DEĞİŞTİ
            )
            session.add(msg)
            session.commit()
        except Exception as e:
            print(f"❌ Chat DB kayıt hatası: {e}")
            session.rollback()
        finally:
            session.close()
    
    def get_history(
        self, 
        user_id: str, 
        session_id: str, 
        limit: int = 50
    ) -> List[Dict]:
        """Kullanıcının chat geçmişini getir"""
        session = self.SessionLocal()
        try:
            messages = session.query(ChatHistory).filter(
                ChatHistory.user_id == user_id,
                ChatHistory.session_id == session_id
            ).order_by(ChatHistory.timestamp.desc()).limit(limit).all()
            
            return [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "metadata": json.loads(msg.extra_data)  # ← Frontend için metadata olarak döndür
                }
                for msg in reversed(messages)  # Eski → Yeni sıralama
            ]
        finally:
            session.close()
    
    def clear_session(self, user_id: str, session_id: str):
        """Belirli bir session'ı sil"""
        session = self.SessionLocal()
        try:
            session.query(ChatHistory).filter(
                ChatHistory.user_id == user_id,
                ChatHistory.session_id == session_id
            ).delete()
            session.commit()
        finally:
            session.close()
    
    def export_history(self, user_id: str, session_id: str) -> str:
        """Chat geçmişini JSON olarak export et"""
        history = self.get_history(user_id, session_id, limit=1000)
        return json.dumps(history, ensure_ascii=False, indent=2)


# Global chat database instance
chat_db = ChatDatabase()