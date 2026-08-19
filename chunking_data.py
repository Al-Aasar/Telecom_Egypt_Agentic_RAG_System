import os
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "We_Raw_Data"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASS", ""),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}

CHUNK_SIZE = 1000       
CHUNK_OVERLAP = 150     

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    separators=["\n\n", "\n", " ", ""]  
)

def setup_target_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS "Chunked_Data" (
            id SERIAL PRIMARY KEY,
            page_id INTEGER REFERENCES crawled_pages(id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            title TEXT,
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            char_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

def process_and_store_chunks():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        setup_target_table(cur)
        conn.commit()

        cur.execute("SELECT id, url, title, body_text FROM crawled_pages WHERE body_text IS NOT NULL AND body_text != '';")
        rows = cur.fetchall()

        print(f"Loaded {len(rows)} pages to process.")

        chunks_to_insert = []
        total_chunks = 0

        for page_id, url, title, body_text in rows:
            split_texts = text_splitter.split_text(body_text)

            for idx, chunk in enumerate(split_texts):
                chunks_to_insert.append((
                    page_id,
                    url,
                    title,
                    idx,
                    chunk,
                    len(chunk)
                ))

            if len(chunks_to_insert) >= 50:
                execute_values(
                    cur,
                    """
                    INSERT INTO "Chunked_Data" (page_id, url, title, chunk_index, chunk_text, char_count)
                    VALUES %s;
                    """,
                    chunks_to_insert
                )
                conn.commit()
                total_chunks += len(chunks_to_insert)
                print(f"Saved {total_chunks} chunks so far...")
                chunks_to_insert.clear()


        if chunks_to_insert:
            execute_values(
                cur,
                """
                INSERT INTO "Chunked_Data" (page_id, url, title, chunk_index, chunk_text, char_count)
                VALUES %s;
                """,
                chunks_to_insert
            )
            conn.commit()
            total_chunks += len(chunks_to_insert)

        print(f"\nProcessing complete. Total chunks saved: {total_chunks}")

    except Exception as e:
        conn.rollback()
        print(f"Error occurred: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    process_and_store_chunks()