import os
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

SRC_DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASS", ""),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}

VECTOR_DB_CONFIG = {
    "dbname": os.getenv("V_DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASS", ""),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
VECTOR_DIM = 1024  

def init_vector_table(v_cur):
    v_cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    
    v_cur.execute(f"""
        CREATE TABLE IF NOT EXISTS document_vectors (
            id SERIAL PRIMARY KEY,
            source_chunk_id INTEGER,
            url TEXT NOT NULL,
            title TEXT,
            chunk_text TEXT NOT NULL,
            embedding vector({VECTOR_DIM}),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    v_cur.execute("""
        CREATE INDEX IF NOT EXISTS doc_vector_hnsw_idx 
        ON document_vectors 
        USING hnsw (embedding vector_cosine_ops);
    """)

def process_and_embed():
    print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}...")

    model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    src_conn = psycopg2.connect(**SRC_DB_CONFIG)
    v_conn = psycopg2.connect(**VECTOR_DB_CONFIG)

    src_cur = src_conn.cursor()
    v_cur = v_conn.cursor()

    try:
        init_vector_table(v_cur)
        v_conn.commit()

        src_cur.execute('SELECT id, url, title, chunk_text FROM "Chunked_Data";')
        rows = src_cur.fetchall()
        print(f"Found {len(rows)} chunks to process.")

        if not rows:
            print("No chunks found in 'Chunked_Data'.")
            return

        batch_size = 32  
        total_rows = len(rows)

        for i in range(0, total_rows, batch_size):
            batch = rows[i:i + batch_size]
            
            chunk_ids = [r[0] for r in batch]
            urls = [r[1] for r in batch]
            titles = [r[2] for r in batch]
            texts = [r[3] for r in batch]

         
            embeddings = model.encode(texts, normalize_embeddings=True)

            insert_records = []
            for c_id, url, title, text, emb in zip(chunk_ids, urls, titles, texts, embeddings):
                insert_records.append((
                    c_id,
                    url,
                    title,
                    text,
                    emb.tolist()
                ))

            execute_values(
                v_cur,
                """
                INSERT INTO document_vectors (source_chunk_id, url, title, chunk_text, embedding)
                VALUES %s;
                """,
                insert_records,
                template="(%s, %s, %s, %s, %s::vector)"
            )
            v_conn.commit()
            print(f"Processed & saved: {min(i + batch_size, total_rows)}/{total_rows} chunks...")

        print("\nAll embeddings generated with BAAI/bge-m3 and saved successfully!")

    except Exception as e:
        v_conn.rollback()
        print(f"Error occurred: {e}")
    finally:
        src_cur.close()
        src_conn.close()
        v_cur.close()
        v_conn.close()

if __name__ == "__main__":
    process_and_embed()