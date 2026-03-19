import sqlite3
import time
from telegram import User
from src.config.settings import DEFAULT_MODEL, DB_FILE

# ------------------------------------------------------------------------------
# Database Initialization & CRUD
# ------------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    with conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                last_seen INTEGER
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                default_model TEXT,
                active_conversation_id INTEGER
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_conversations (
                conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                conversation_name TEXT NOT NULL,
                model TEXT,
                system_prompt TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp INTEGER NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS conversation_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                summary TEXT NOT NULL,
                timestamp INTEGER NOT NULL
            )
        """)
    conn.close()

def upsert_user(telegram_user: User):
    user_id = telegram_user.id
    username = telegram_user.username or ""
    first_name = telegram_user.first_name or ""
    last_name = telegram_user.last_name or ""
    last_seen = int(time.time())
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                last_seen=excluded.last_seen
        """, (user_id, username, first_name, last_name, last_seen))
        c.execute("""
            INSERT INTO user_settings (user_id, default_model, active_conversation_id)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO NOTHING
        """, (user_id, DEFAULT_MODEL, None))

def get_user_settings(user_id: int) -> dict:
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT default_model, active_conversation_id FROM user_settings WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        if row:
            return {"default_model": row[0], "active_conversation_id": row[1]}
    return {"default_model": DEFAULT_MODEL, "active_conversation_id": None}

def set_user_setting(user_id: int, field: str, value):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        query = f"UPDATE user_settings SET {field} = ? WHERE user_id = ?"
        c.execute(query, (value, user_id))

def create_conversation(user_id: int, name: str, model: str = None) -> int:
    if not model:
        model = get_user_settings(user_id)["default_model"]
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO user_conversations (user_id, conversation_name, model, system_prompt)
            VALUES (?, ?, ?, ?)
        """, (user_id, name, model, ""))
        return c.lastrowid

def get_user_conversations(user_id: int):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT conversation_id, conversation_name, model, system_prompt
            FROM user_conversations
            WHERE user_id = ?
            ORDER BY conversation_id ASC
        """, (user_id,))
        rows = c.fetchall()
    return [
        {
            "conversation_id": r[0],
            "conversation_name": r[1],
            "model": r[2],
            "system_prompt": r[3]
        }
        for r in rows
    ]

def switch_conversation(user_id: int, conversation_id: int):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT conversation_id FROM user_conversations
            WHERE conversation_id = ? AND user_id = ?
        """, (conversation_id, user_id))
        if c.fetchone():
            set_user_setting(user_id, "active_conversation_id", conversation_id)
            return True
    return False

def update_conversation_model(conversation_id: int, model: str):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE user_conversations SET model = ? WHERE conversation_id = ?", (model, conversation_id))

def update_conversation_system_prompt(conversation_id: int, prompt: str):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE user_conversations SET system_prompt = ? WHERE conversation_id = ?", (prompt, conversation_id))

def get_messages(conversation_id: int) -> list:
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT role, content FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp ASC
        """, (conversation_id,))
        return [{"role": r[0], "content": r[1]} for r in c.fetchall()]

def append_message(conversation_id: int, role: str, content: str):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, int(time.time()))
        )

def clear_conversation_messages(conversation_id: int):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))

def append_summary(conversation_id: int, summary: str):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO conversation_summary (conversation_id, summary, timestamp)
            VALUES (?, ?, ?)
        """, (conversation_id, summary, int(time.time())))

def get_summaries(conversation_id: int) -> list:
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT summary FROM conversation_summary
            WHERE conversation_id = ?
            ORDER BY timestamp ASC
        """, (conversation_id,))
        return [r[0] for r in c.fetchall()]
