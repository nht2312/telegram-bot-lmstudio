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

# ------------------------------------------------------------------------------
# Statistics Functions
# ------------------------------------------------------------------------------
def init_usage_log_table():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                conversation_id INTEGER,
                model TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                response_time_ms INTEGER,
                timestamp INTEGER NOT NULL
            )
        """)

def log_usage(user_id: int, conversation_id: int, model: str, 
              prompt_tokens: int, completion_tokens: int, total_tokens: int,
              response_time_ms: int):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO usage_log 
            (user_id, conversation_id, model, prompt_tokens, completion_tokens, 
             total_tokens, response_time_ms, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, conversation_id, model, prompt_tokens, completion_tokens,
              total_tokens, response_time_ms, int(time.time())))

def get_user_stats(user_id: int) -> dict:
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM messages m JOIN user_conversations uc ON m.conversation_id = uc.conversation_id WHERE uc.user_id = ?", (user_id,))
        total_messages = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM user_conversations WHERE user_id = ?", (user_id,))
        total_conversations = c.fetchone()[0]
        
        c.execute("""
            SELECT COALESCE(SUM(total_tokens), 0), COALESCE(SUM(prompt_tokens), 0),
                   COALESCE(SUM(completion_tokens), 0), COALESCE(AVG(response_time_ms), 0), COUNT(*)
            FROM usage_log WHERE user_id = ?
        """, (user_id,))
        row = c.fetchone()
        
        c.execute("""
            SELECT model, COUNT(*) FROM usage_log WHERE user_id = ?
            GROUP BY model ORDER BY COUNT(*) DESC LIMIT 1
        """, (user_id,))
        top_model_row = c.fetchone()
        
        return {
            "total_messages": total_messages,
            "total_conversations": total_conversations,
            "total_tokens": row[0],
            "prompt_tokens": row[1],
            "completion_tokens": row[2],
            "avg_response_time_ms": round(row[3], 0),
            "total_api_calls": row[4],
            "top_model": top_model_row[0] if top_model_row else None
        }

def get_global_stats() -> dict:
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM user_conversations")
        total_conversations = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM messages")
        total_messages = c.fetchone()[0]
        
        c.execute("""
            SELECT COALESCE(SUM(total_tokens), 0), COALESCE(SUM(prompt_tokens), 0),
                   COALESCE(SUM(completion_tokens), 0), COALESCE(AVG(response_time_ms), 0), COUNT(*)
            FROM usage_log
        """)
        row = c.fetchone()
        
        c.execute("SELECT model, COUNT(*) FROM usage_log GROUP BY model ORDER BY COUNT(*) DESC")
        model_usage = c.fetchall()
        
        c.execute("""
            SELECT u.user_id, u.username, u.first_name, COALESCE(SUM(ul.total_tokens), 0) as total_tokens, COUNT(ul.id) as api_calls
            FROM users u LEFT JOIN usage_log ul ON u.user_id = ul.user_id
            GROUP BY u.user_id ORDER BY total_tokens DESC LIMIT 10
        """)
        top_users = c.fetchall()
        
        return {
            "total_users": total_users,
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "total_tokens": row[0],
            "prompt_tokens": row[1],
            "completion_tokens": row[2],
            "avg_response_time_ms": round(row[3], 1) if row[3] else 0,
            "total_api_calls": row[4],
            "model_usage": model_usage,
            "top_users": top_users
        }

def get_conversation_stats(conversation_id: int) -> dict:
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (conversation_id,))
        message_count = c.fetchone()[0]
        
        c.execute("""
            SELECT COALESCE(SUM(total_tokens), 0), COALESCE(SUM(prompt_tokens), 0),
                   COALESCE(SUM(completion_tokens), 0), COUNT(*)
            FROM usage_log WHERE conversation_id = ?
        """, (conversation_id,))
        row = c.fetchone()
        
        c.execute("SELECT COUNT(*) FROM conversation_summary WHERE conversation_id = ?", (conversation_id,))
        summary_count = c.fetchone()[0]
        
        return {
            "message_count": message_count,
            "total_tokens": row[0],
            "prompt_tokens": row[1],
            "completion_tokens": row[2],
            "api_calls": row[3],
            "summaries_count": summary_count
        }
