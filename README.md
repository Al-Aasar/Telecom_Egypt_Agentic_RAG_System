# WE (Telecom Egypt) RAG Chat System

An intelligent assistant built on **RAG (Retrieval-Augmented Generation)** that answers customer questions relying **exclusively** on the official content of [te.eg](https://te.eg) — no hallucination, no going outside the scope of the company's services.

## Pipeline Overview

```
te.eg  ──scrape──▶  crawled_pages   ──chunk──▶  Chunked_Data   ──embed──▶  document_vectors
                     (Postgres)                  (Postgres)                (Postgres + pgvector)
                                                                                   │
                                                                                   ▼
                                                                    ┌──────────────────────────┐
                                                                    │   Hybrid Retrieval        │
                                                                    │  Dense (pgvector) +       │
                                                                    │  Sparse (full-text) → RRF │
                                                                    └──────────┬────────────────┘
                                                                               ▼
                                                                    ┌──────────────────────────┐
                                                                    │  Groq API (Llama/GPT-OSS) │
                                                                    │  Grounded generation +    │
                                                                    │  topic guardrails         │
                                                                    └──────────┬────────────────┘
                                                                               ▼
                                                                    Postgres checkpointing
                                                                    (chat_sessions/messages)
                                                                               ▼
                                                                    Chat interface (HTML/CSS/JS)
```

## Stages

| File | Function |
|---|---|
| `scrape_te_eg.py` | Crawls the te.eg website (respecting `robots.txt`) and saves the pages into the `crawled_pages` table |
| `chunking_data.py` | Splits the scraped text into chunks (`RecursiveCharacterTextSplitter`) and saves them into `Chunked_Data` |
| `embed_data.py` | Converts the chunks into embeddings using the `BAAI/bge-m3` model and saves them into `document_vectors` (pgvector) |
| `app.py`, `db.py`, `hybrid_retrieval.py`, `llm_groq.py`, `chat_memory.py`, `static/` | Retrieval + generation + UI layer |

## Key Features

- **Hybrid Search**: Combines Dense (semantic, pgvector) + Sparse (lexical, Postgres full-text) search using **Reciprocal Rank Fusion** — covers both meaning-based and literal keyword search cases.
- **Grounded generation**: The model (via Groq) answers only from the retrieved context, with strict instructions against hallucination and going off-topic.
- **Topic guardrails**: Two protection layers — rejection before the query even reaches the model if there's no genuinely relevant content (via the `MIN_DENSE_SCORE` threshold), and strict system-prompt instructions that prevent answering from general knowledge or responding to any prompt injection.
- **Checkpointing**: Every conversation and its messages are saved in Postgres (`chat_sessions` / `chat_messages`), with the ability to retrieve or delete any past conversation.
- **Chat interface**: Toggleable Arabic/English RTL UI, self-contained markdown rendering (no reliance on any external CDN), and source display for every answer.

## Tech Stack

- **Backend**: Python, FastAPI, psycopg2
- **DB**: PostgreSQL + [pgvector](https://github.com/pgvector/pgvector) extension
- **Embeddings**: `BAAI/bge-m3` (sentence-transformers)
- **LLM**: Groq API (open models such as `openai/gpt-oss-120b`)
- **Frontend**: HTML / CSS / vanilla JS (no frameworks)

## Quick Start

```bash
# 1) The data pipeline (run once, or whenever you want to refresh the data)
python scrape_te_eg.py
python chunking_data.py
python embed_data.py

# 2) The chat layer
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env   # then edit your details: DB + GROQ_API_KEY

python db.py            # one-time: sparse search index + checkpointing tables
uvicorn app:app --reload --port 8000
```

Then open `http://localhost:8000`.

## Project Structure

```
.
├── scrape_te_eg.py
├── chunking_data.py
├── embed_data.py
├── app.py                 # FastAPI: /api/chat, /api/sessions, DELETE session
├── db.py                  # schema: sparse index + checkpointing tables
├── hybrid_retrieval.py    # dense + sparse search + RRF fusion
├── llm_groq.py            # Groq LLM call + system prompt / guardrails
├── chat_memory.py         # session/message persistence
├── requirements.txt
├── .env.example
├── README.md
└── static/
    ├── index.html
    ├── style.css
    └── script.js
```

## Notes

- `.env` is not pushed to GitHub (it's listed in `.gitignore`) — everyone running the project needs to make their own copy from `.env.example`.
- The default Groq model changes over time (deprecations); if you run into `model_not_found`, check [Groq deprecations](https://console.groq.com/docs/deprecations) and update `GROQ_MODEL` in `.env`.

## License

MIT
