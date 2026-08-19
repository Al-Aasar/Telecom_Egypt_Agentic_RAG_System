from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from hybrid_retrieval import hybrid_search
from llm_groq import generate_answer
from chat_memory import (
    create_session,
    save_message,
    load_history,
    list_sessions,
    get_session_messages,
    delete_session,
)
from db import init_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_schema()
    yield


app = FastAPI(title="TE.eg RAG Chat", lifespan=lifespan)

OUT_OF_SCOPE_MESSAGE = (
    "أنا مساعد متخصص في خدمات TE فقط، ومقدرش أجاوب على أسئلة خارج نطاق "
    "الموقع والخدمات المتاحة عليه. جرّب تسأل عن باقات الإنترنت، الفواتير، "
    "الخدمات، أو أي حاجة متعلقة بـ TE.\n\n"
    "I'm a TE-services assistant only, and can't answer questions outside "
    "that scope. Try asking about internet packages, billing, or TE services."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[dict]


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty.")

    session_id = req.session_id or create_session(title=req.message[:60])

    history = load_history(session_id)
    chunks = hybrid_search(req.message)


    if not chunks:
        answer = OUT_OF_SCOPE_MESSAGE
        sources = []
    else:
        answer = generate_answer(req.message, chunks, history=history)
        sources = [
            {"url": c["url"], "title": c["title"], "score": round(c["rrf_score"], 4)}
            for c in chunks
        ]

    save_message(session_id, "user", req.message)
    save_message(session_id, "assistant", answer, retrieved_sources=sources)

    return ChatResponse(session_id=session_id, answer=answer, sources=sources)


@app.get("/api/sessions")
def get_sessions():
    return list_sessions()


@app.get("/api/sessions/{session_id}/messages")
def get_messages(session_id: str):
    return get_session_messages(session_id)


@app.delete("/api/sessions/{session_id}")
def remove_session(session_id: str):
    deleted = delete_session(session_id)
    if not deleted:
        raise HTTPException(404, "Session not found.")
    return {"deleted": True}


# --- serve the frontend ---
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
