
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import (
    APP_NAME,
    FRONTEND_DIR,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)
from app.conversation import (
    create_conversation_id,
    generate_response,
    initialise_database,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialise_database()
    yield


app = FastAPI(
    title=APP_NAME,
    description="Local AI companion",
    version="0.1.0",
    lifespan=lifespan,
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    conversation_id: str | None = None


@app.get("/api/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{OLLAMA_BASE_URL}/api/tags"
            )
            response.raise_for_status()

        return {
            "status": "online",
            "ollama": "connected",
            "model": OLLAMA_MODEL,
        }

    except httpx.HTTPError:
        return {
            "status": "degraded",
            "ollama": "unavailable",
            "model": OLLAMA_MODEL,
        }


@app.post("/api/chat")
async def chat(request: ChatRequest):
    conversation_id = (
        request.conversation_id or create_conversation_id()
    )

    try:
        reply = await generate_response(
            conversation_id,
            request.message.strip(),
        )

        return {
            "conversation_id": conversation_id,
            "reply": reply,
        }

    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=503,
            detail=f"Could not communicate with Ollama: {error}",
        ) from error

    except (KeyError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail="The model returned an unexpected response.",
        ) from error


app.mount(
    "/",
    StaticFiles(directory=FRONTEND_DIR, html=True),
    name="frontend",
)
