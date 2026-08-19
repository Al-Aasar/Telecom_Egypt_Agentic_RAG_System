from db import get_connection
import json


HISTORY_WINDOW = 10 


def create_session(title: str | None = None) -> str:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO chat_sessions (title) VALUES (%s) RETURNING id;",
            (title,),
        )
        session_id = cur.fetchone()[0]
        conn.commit()
        return str(session_id)
    finally:
        cur.close()
        conn.close()


def save_message(session_id: str, role: str, content: str, retrieved_sources=None):
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO chat_messages (session_id, role, content, retrieved_sources)
            VALUES (%s, %s, %s, %s);
            """,
            (session_id, role, content, json.dumps(retrieved_sources) if retrieved_sources else None),
        )
        cur.execute(
            "UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s;",
            (session_id,),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


def load_history(session_id: str, limit: int = HISTORY_WINDOW):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT role, content FROM (
                SELECT role, content, created_at
                FROM chat_messages
                WHERE session_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            ) sub
            ORDER BY created_at ASC;
            """,
            (session_id, limit),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return [{"role": r[0], "content": r[1]} for r in rows]


def delete_session(session_id: str):
    """chat_messages has ON DELETE CASCADE on session_id, so deleting the
    session row removes its messages automatically."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM chat_sessions WHERE id = %s;", (session_id,))
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    finally:
        cur.close()
        conn.close()


def list_sessions():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM chat_sessions
            ORDER BY updated_at DESC;
            """
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return [
        {"id": str(r[0]), "title": r[1], "created_at": r[2].isoformat(), "updated_at": r[3].isoformat()}
        for r in rows
    ]


def get_session_messages(session_id: str):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT role, content, retrieved_sources, created_at
            FROM chat_messages
            WHERE session_id = %s
            ORDER BY created_at ASC;
            """,
            (session_id,),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return [
        {"role": r[0], "content": r[1], "retrieved_sources": r[2], "created_at": r[3].isoformat()}
        for r in rows
    ]
