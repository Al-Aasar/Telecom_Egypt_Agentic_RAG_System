import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("V_DB_NAME", os.getenv("DB_NAME", "postgres")),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASS", ""),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "sslmode": os.getenv("DB_SSLMODE", "prefer"),
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def init_schema():
    """Creates everything the retrieval + chat layer needs on top of
    the existing document_vectors table (from embed_data.py):
      - a tsvector column + GIN index on document_vectors for sparse/lexical search
      - chat_sessions / chat_messages for checkpointing conversations
    Safe to run multiple times.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        ts_config = os.getenv("TS_CONFIG", "simple")

        cur.execute("""
            ALTER TABLE document_vectors
            ADD COLUMN IF NOT EXISTS chunk_tsv tsvector;
        """)
        cur.execute(f"""
            UPDATE document_vectors
            SET chunk_tsv = to_tsvector('{ts_config}', coalesce(chunk_text, ''))
            WHERE chunk_tsv IS NULL;
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS document_vectors_tsv_idx
            ON document_vectors USING gin (chunk_tsv);
        """)
        cur.execute(f"""
            CREATE OR REPLACE FUNCTION document_vectors_tsv_trigger() RETURNS trigger AS $$
            begin
              new.chunk_tsv := to_tsvector('{ts_config}', coalesce(new.chunk_text, ''));
              return new;
            end
            $$ LANGUAGE plpgsql;
        """)
        cur.execute("""
            DROP TRIGGER IF EXISTS trg_document_vectors_tsv ON document_vectors;
        """)
        cur.execute("""
            CREATE TRIGGER trg_document_vectors_tsv
            BEFORE INSERT OR UPDATE OF chunk_text ON document_vectors
            FOR EACH ROW EXECUTE FUNCTION document_vectors_tsv_trigger();
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id BIGSERIAL PRIMARY KEY,
                session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                retrieved_sources JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS chat_messages_session_idx
            ON chat_messages (session_id, created_at);
        """)

        conn.commit()
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    init_schema()
    print("Schema ready: sparse index on document_vectors + chat_sessions/chat_messages.")
