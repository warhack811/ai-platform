from typing import List
from datetime import datetime, timedelta
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str        # "user" veya "assistant"
    content: str
    timestamp: datetime
    message_type: str = "text"


class ChatMemory(BaseModel):
    user_id: str
    messages: List[ChatMessage] = []
    created_at: datetime = datetime.now()
    last_activity: datetime = datetime.now()
    context_summary: str = ""


class ChatMemoryManager:
    """
    Kullanıcı + session bazlı sohbet hafızası yöneticisi.
    - Son X mesajı tutar
    - 2 saatten eski oturumları sıfırlar
    """

    def __init__(self):
        self.memories = {}
        self.max_messages_per_user = 20
        self.session_timeout = timedelta(hours=2)

    def get_memory_key(self, user_id: str, session_id: str) -> str:
        return f"{user_id}_{session_id}"

    def get_user_memory(self, user_id: str, session_id: str) -> ChatMemory:
        memory_key = self.get_memory_key(user_id, session_id)

        if memory_key not in self.memories:
            self.memories[memory_key] = ChatMemory(
                user_id=user_id,
                messages=[],
                created_at=datetime.now(),
                last_activity=datetime.now()
            )

        memory = self.memories[memory_key]

        # Oturum süresi dolmuşsa sıfırla
        if datetime.now() - memory.last_activity > self.session_timeout:
            self.memories[memory_key] = ChatMemory(
                user_id=user_id,
                messages=[],
                created_at=datetime.now(),
                last_activity=datetime.now()
            )
            memory = self.memories[memory_key]

        return memory

    def add_message(self, user_id: str, session_id: str, role: str, content: str):
        memory = self.get_user_memory(user_id, session_id)

        new_message = ChatMessage(
            role=role,
            content=content,
            timestamp=datetime.now(),
            message_type="text"
        )

        memory.messages.append(new_message)
        memory.last_activity = datetime.now()

        # Mesaj çok artarsa eskileri kes
        if len(memory.messages) > self.max_messages_per_user:
            memory.messages = memory.messages[-self.max_messages_per_user:]

    def get_conversation_context(
        self,
        user_id: str,
        session_id: str,
        max_messages: int = 12
    ) -> str:
        memory = self.get_user_memory(user_id, session_id)

        if not memory.messages:
            return ""

        recent_messages = memory.messages[-max_messages:]

        lines = []
        for msg in recent_messages:
            if msg.role == "user":
                lines.append(f"KULLANICI: {msg.content}")
            else:
                lines.append(f"ASİSTANT: {msg.content}")

        return "\n".join(lines)

    def clear_memory(self, user_id: str, session_id: str):
        memory_key = self.get_memory_key(user_id, session_id)
        if memory_key in self.memories:
            del self.memories[memory_key]


# Global sohbet hafızası yöneticisi
chat_memory_manager = ChatMemoryManager()
