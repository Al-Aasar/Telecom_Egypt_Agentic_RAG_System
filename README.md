# WE (Telecom Egypt) RAG Chat System

مساعد ذكي مبني على **RAG (Retrieval-Augmented Generation)** بيجاوب على أسئلة العملاء بالاعتماد **حصريًا** على محتوى موقع [te.eg](https://te.eg) الرسمي — من غير هلوسة، ومن غير خروج عن نطاق خدمات الشركة.

## نظرة عامة على الـ Pipeline

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
                                                                    واجهة شات (HTML/CSS/JS)
```

## المراحل

| الملف | الوظيفة |
|---|---|
| `scrape_te_eg.py` | بيعمل crawl لموقع te.eg (respecting `robots.txt`) ويحفظ الصفحات في جدول `crawled_pages` |
| `chunking_data.py` | بيقسّم النصوص المكشوطة لـ chunks (`RecursiveCharacterTextSplitter`) ويحفظها في `Chunked_Data` |
| `embed_data.py` | بيحوّل الـ chunks لـ embeddings بموديل `BAAI/bge-m3` ويحفظها في `document_vectors` (pgvector) |
| `rag_chat/` | طبقة الـ retrieval + generation + الواجهة (تفاصيلها في [`rag_chat/README.md`](rag_chat/README.md)) |

## المميزات الرئيسية

- **Hybrid Search**: دمج Dense (semantic, pgvector) + Sparse (lexical, Postgres full-text) بـ **Reciprocal Rank Fusion** — بيغطي حالات البحث بالمعنى وبالكلمة الحرفية مع بعض.
- **Grounded generation**: الموديل (عن طريق Groq) بيجاوب من الـ context المسترجع بس، مع تعليمات صارمة ضد الهلوسة والخروج عن الموضوع.
- **Topic guardrails**: طبقتين حماية — رفض قبل ما يوصل للموديل أصلاً لو مفيش محتوى مرتبط فعليًا (عتبة `MIN_DENSE_SCORE`)، وتعليمات صارمة في الـ system prompt تمنع الإجابة من المعرفة العامة أو الاستجابة لأي prompt injection.
- **Checkpointing**: كل محادثة ورسائلها بتتحفظ في Postgres (`chat_sessions` / `chat_messages`)، مع إمكانية استرجاع أو حذف أي محادثة قديمة.
- **واجهة شات**: RTL عربي/إنجليزي قابلة للتبديل، markdown rendering داخلي (من غير أي اعتماد على CDN خارجي)، وعرض مصادر كل إجابة.

## التقنيات المستخدمة

- **Backend**: Python, FastAPI, psycopg2
- **DB**: PostgreSQL + [pgvector](https://github.com/pgvector/pgvector) extension
- **Embeddings**: `BAAI/bge-m3` (sentence-transformers)
- **LLM**: Groq API (نماذج مفتوحة زي `openai/gpt-oss-120b`)
- **Frontend**: HTML / CSS / vanilla JS (بدون frameworks)

## التشغيل السريع

```bash
# 1) الـ pipeline (مرة واحدة، أو كل ما تحب تحدّث البيانات)
python scrape_te_eg.py
python chunking_data.py
python embed_data.py

# 2) طبقة الشات
cd rag_chat
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env   # وعدّل بياناتك: DB + GROQ_API_KEY

python db.py            # مرة واحدة: فهرس sparse search + جداول checkpointing
uvicorn app:app --reload --port 8000
```

بعدها افتح `http://localhost:8000`.

تفاصيل أكتر عن طبقة الشات (البنية، الـ env variables، الجاردريلز) في [`rag_chat/README.md`](rag_chat/README.md).

## بنية المشروع

```
.
├── scrape_te_eg.py
├── chunking_data.py
├── embed_data.py
└── rag_chat/
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

## ملاحظات

- `.env` مش بيترفع على GitHub (متضاف في `.gitignore`) — كل حد بيشغّل المشروع لازم يعمل نسخته الخاصة من `.env.example`.
- الموديل الافتراضي على Groq بيتغيّر بمرور الوقت (deprecations)، لو واجهت `model_not_found` راجع [Groq deprecations](https://console.groq.com/docs/deprecations) وحدّث `GROQ_MODEL` في `.env`.

## License

MIT
