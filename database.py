"""SQLite database module for VN CG Viewer application."""

import os
import sqlite3
from pathlib import Path
from typing import Generator

# Resolve DB path from environment so this module works on Vercel and locally.
# On Vercel, set VN_CG_DB_PATH to a writable path such as /tmp/data.db.
_DEFAULT_DB_PATH = Path(__file__).parent / "data.db"
DB_PATH = Path(os.environ.get("VN_CG_DB_PATH", str(_DEFAULT_DB_PATH)))

# Ensure the parent directory exists at runtime (skipped silently if read-only).
try:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

DEFAULT_TAGS = [
    # Scene types
    ("cg_scene", "scene_type"),
    ("character_art", "scene_type"),
    ("background", "scene_type"),
    ("sprite_leak", "scene_type"),
    ("ui_element", "scene_type"),
    # Content
    ("ecchi", "content"),
    ("explicit", "content"),
    ("sfw", "content"),
    ("questionable", "content"),
    # Quality
    ("high_res", "quality"),
    ("low_res", "quality"),
    ("duplicate", "quality"),
    ("corrupted", "quality"),
]


def get_db() -> sqlite3.Connection:
    """Get a database connection with Row factory.

    Returns:
        sqlite3.Connection: Database connection with row_factory set to sqlite3.Row
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.execute("PRAGMA busy_timeout = 10000")  # 10 seconds
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database with all required tables and seed default tags."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Set journal mode to WAL for better concurrency
        cursor.execute("PRAGMA journal_mode=WAL")

        # Create games table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                path TEXT NOT NULL,
                image_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create images table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL REFERENCES games(id),
                filename TEXT NOT NULL,
                filepath TEXT UNIQUE NOT NULL,
                width INTEGER,
                height INTEGER,
                file_size INTEGER,
                format TEXT,
                has_alpha BOOLEAN DEFAULT FALSE,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending','accepted','rejected','flagged','skipped')),
                rating INTEGER CHECK(rating IS NULL OR (rating >= 1 AND rating <= 5)),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP
            )
        """)

        # Create tags table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                category TEXT DEFAULT 'custom'
            )
        """)

        # Create image_tags table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS image_tags (
                image_id INTEGER NOT NULL REFERENCES images(id),
                tag_id INTEGER NOT NULL REFERENCES tags(id),
                PRIMARY KEY (image_id, tag_id)
            )
        """)

        # Create action_log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                image_id INTEGER NOT NULL REFERENCES images(id),
                action TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT,
                old_rating INTEGER,
                new_rating INTEGER,
                undone BOOLEAN DEFAULT FALSE
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_images_game
            ON images(game_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_images_status
            ON images(status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_images_filepath
            ON images(filepath)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_action_log_session
            ON action_log(session_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_image_tags_image
            ON image_tags(image_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_image_tags_tag
            ON image_tags(tag_id)
        """)

        # Seed default tags
        for tag_name, tag_category in DEFAULT_TAGS:
            cursor.execute(
                "INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)",
                (tag_name, tag_category)
            )

        conn.commit()
    finally:
        conn.close()


def insert_game(name: str, path: str) -> int:
    """Insert a game into the database.

    Args:
        name: Game name
        path: Path to game directory

    Returns:
        int: The game id, or None if duplicate

    Raises:
        sqlite3.IntegrityError: If game name is not unique
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO games (name, path, image_count) VALUES (?, ?, ?)",
            (name, path, 0)
        )
        conn.commit()
        # Get the id of inserted game
        cursor.execute("SELECT id FROM games WHERE name = ?", (name,))
        result = cursor.fetchone()
        return result[0] if result else None
    finally:
        conn.close()


def get_db_context() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections.

    Yields:
        sqlite3.Connection: Database connection
    """
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()
