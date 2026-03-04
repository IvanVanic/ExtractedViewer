"""Routes for game management and scanning."""

import logging
import os
from pathlib import Path
from typing import Any

import sqlite3
from fastapi import APIRouter, HTTPException, Query

from database import get_db
from models import GameResponse, GameDetailResponse
from services.scanner import scan_cleaned_directory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/games", tags=["games"])


@router.get("/", response_model=list[GameResponse])
def list_games() -> list[GameResponse]:
    """List all games with image and review counts.

    Returns:
        List of GameResponse objects with game info and counts.

    Raises:
        HTTPException: If database query fails.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                g.id,
                g.name,
                g.image_count,
                COUNT(CASE WHEN i.status != 'pending' THEN 1 END) as reviewed_count,
                NULL as thumbnail_url
            FROM games g
            LEFT JOIN images i ON g.id = i.game_id
            GROUP BY g.id, g.name, g.image_count
            ORDER BY g.name
        """)

        rows = cursor.fetchall()
        conn.close()

        games = []
        for row in rows:
            games.append(GameResponse(
                id=row["id"],
                name=row["name"],
                image_count=row["image_count"],
                reviewed_count=row["reviewed_count"] or 0,
                thumbnail_url=None
            ))

        return games
    except Exception as e:
        logger.error(f"Error listing games: {e}")
        raise HTTPException(status_code=500, detail="Failed to list games")


@router.get("/{game_id}", response_model=GameDetailResponse)
def get_game(game_id: int) -> GameDetailResponse:
    """Get detailed information about a specific game.

    Args:
        game_id: ID of the game to retrieve.

    Returns:
        GameDetailResponse with game info and action counts.

    Raises:
        HTTPException: If game not found or database query fails.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                g.id,
                g.name,
                g.image_count,
                COUNT(CASE WHEN i.status != 'pending' THEN 1 END) as reviewed_count,
                COUNT(CASE WHEN i.status = 'accepted' THEN 1 END) as accepted_count,
                COUNT(CASE WHEN i.status = 'rejected' THEN 1 END) as rejected_count,
                COUNT(CASE WHEN i.status = 'flagged' THEN 1 END) as flagged_count
            FROM games g
            LEFT JOIN images i ON g.id = i.game_id
            WHERE g.id = ?
            GROUP BY g.id, g.name, g.image_count
        """, (game_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Game not found")

        return GameDetailResponse(
            id=row["id"],
            name=row["name"],
            image_count=row["image_count"],
            reviewed_count=row["reviewed_count"] or 0,
            accepted_count=row["accepted_count"] or 0,
            rejected_count=row["rejected_count"] or 0,
            flagged_count=row["flagged_count"] or 0,
            thumbnail_url=None
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting game {game_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get game details")


# Separate router for scan endpoint
scan_router = APIRouter(prefix="/api", tags=["scan"])


@scan_router.post("/scan")
def trigger_scan() -> dict[str, Any]:
    """Trigger a directory scan to index images from cleaned directory.

    Scans the cleaned directory for new VN CG images and indexes them into
    the database. Updates game records with image counts.

    Returns:
        Dictionary with scan statistics:
        - games_found: Number of games discovered
        - images_found: Total images in cleaned directory
        - new_images: Number of new images added
        - skipped: Number of images already in database

    Raises:
        HTTPException: If scan fails.
    """
    try:
        # Get database path from environment variable (set VN_CG_DB_PATH in
        # Vercel project settings). Falls back to data.db beside this package.
        _default_db = str(Path(__file__).parent.parent / "data.db")
        db_path_str = os.getenv("VN_CG_DB_PATH", _default_db)
        db_path = Path(db_path_str)
        stats = scan_cleaned_directory(db_path)

        logger.info(f"Scan completed with stats: {stats}")
        return stats
    except Exception as e:
        logger.error(f"Error during scan: {e}")
        raise HTTPException(status_code=500, detail="Scan failed")
