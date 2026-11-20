import logging
import sqlite3
import uuid
from datetime import datetime, timezone

import httpx

from app.config import (
    DATABASE_PATH,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
)

logger = logging.getLogger("athena.conversation")

SYSTEM_PROMPT = """
You are Athena, a knowledgeable and thoughtful AI companion.

Your character:
- Composed, articulate, warm and intellectually curious.
- Speak naturally rather than sounding like a formal report.
- Explain complex subjects clearly without unnecessarily
  oversimplifying them.
- Challenge incorrect assumptions respectfully.
- Ask useful questions when clarification is necessary.
- Be honest about uncertainty and limitations.
- Never invent facts, sources, legal authorities or evidence.

Your role:
Help the user learn, reason, research, create and solve problems.
You are a general-purpose companion, not a specialised tutor.

Do not pretend to have feelings, experiences or capabilities
that you do not possess.

Maintain continuity with the conversation.
"""

def initialise_database():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation
            ON messages(conversation_id, id)
        """)
        connection.commit()


def save_message(conversation_id, role, content):
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            INSERT INTO messages
            (conversation_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                conversation_id,
                role,
                content,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()


def get_history(conversation_id, limit=12):
    with sqlite3.connect(DATABASE_PATH) as connection:
        rows = connection.execute(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()

    return [
        {"role": role, "content": content}
        for role, content in reversed(rows)
    ]


async def generate_response(conversation_id, user_message):
    history = get_history(conversation_id)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": 1000,
            "temperature": 0.7,
        },
    }

    # Persist the user message BEFORE model inference so conversation
    # history is not lost if the Ollama call fails.
    save_message(conversation_id, "user", user_message)

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
        )
        response.raise_for_status()
        result = response.json()

    assistant_message = result["message"]["content"]

    # Capture Ollama response metadata for diagnostics.
    # Fields: done, done_reason, total_duration, load_duration,
    # prompt_eval_count, eval_count, eval_duration.
    ollama_metadata = {
        "done": result.get("done"),
        "done_reason": result.get("done_reason"),
        "total_duration": result.get("total_duration"),
        "load_duration": result.get("load_duration"),
        "prompt_eval_count": result.get("prompt_eval_count"),
        "eval_count": result.get("eval_count"),
        "eval_duration": result.get("eval_duration"),
    }

    logger.info(
        "Ollama response model=%s done=%s done_reason=%s "
        "eval_count=%s eval_duration_ms=%s "
        "prompt_eval_count=%s total_duration_ms=%s",
        OLLAMA_MODEL,
        ollama_metadata["done"],
        ollama_metadata["done_reason"],
        ollama_metadata["eval_count"],
        ollama_metadata["eval_duration"],
        ollama_metadata["prompt_eval_count"],
        ollama_metadata["total_duration"],
    )

    # Persist the assistant response only after successful generation.
    save_message(conversation_id, "assistant", assistant_message)

    return assistant_message, ollama_metadata


def create_conversation_id():
    return str(uuid.uuid4())
