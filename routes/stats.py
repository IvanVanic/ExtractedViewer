"""Routes for statistics and analytics."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from database import get_db
from models import StatsResponse, GameStats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/")
def get_global_stats() -> StatsResponse:
    """Get global statistics across all games.

    Returns:
        StatsResponse with total counts, reviewed counts, and per-game breakdown.

    Raises:
        HTTPException: If database query fails.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Get global stats
        cursor.execute("""
            SELECT
                COUNT(*) as total_images,
                COUNT(CASE WHEN status != 'pending' THEN 1 END) as reviewed,
                COUNT(CASE WHEN status = 'accepted' THEN 1 END) as accepted,
                COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected,
                COUNT(CASE WHEN status = 'flagged' THEN 1 END) as flagged
            FROM images
        """)

        global_row = cursor.fetchone()

        total_images = global_row["total_images"]
        reviewed = global_row["reviewed"] or 0
        accepted = global_row["accepted"] or 0
        rejected = global_row["rejected"] or 0
        flagged = global_row["flagged"] or 0

        # Get per-game stats
        cursor.execute("""
            SELECT
                g.id as game_id,
                g.name as game_name,
                COUNT(i.id) as total,
                COUNT(CASE WHEN i.status != 'pending' THEN 1 END) as reviewed,
                COUNT(CASE WHEN i.status = 'accepted' THEN 1 END) as accepted,
                COUNT(CASE WHEN i.status = 'rejected' THEN 1 END) as rejected,
                COUNT(CASE WHEN i.status = 'flagged' THEN 1 END) as flagged
            FROM games g
            LEFT JOIN images i ON g.id = i.game_id
            GROUP BY g.id, g.name
            ORDER BY g.name
        """)

        game_stats_rows = cursor.fetchall()
        conn.close()

        by_game = [
            GameStats(
                game_id=row["game_id"],
                game_name=row["game_name"],
                total=row["total"] or 0,
                reviewed=row["reviewed"] or 0,
                accepted=row["accepted"] or 0,
                rejected=row["rejected"] or 0,
                flagged=row["flagged"] or 0
            )
            for row in game_stats_rows
        ]

        return StatsResponse(
            total_images=total_images,
            reviewed=reviewed,
            accepted=accepted,
            rejected=rejected,
            flagged=flagged,
            by_game=by_game
        )
    except Exception as e:
        logger.error(f"Error getting global stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")


@router.get("/{game_id}")
def get_game_stats(game_id: int) -> GameStats:
    """Get statistics for a specific game.

    Args:
        game_id: ID of the game.

    Returns:
        GameStats with counts for the specified game.

    Raises:
        HTTPException: If game not found or database query fails.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                g.id as game_id,
                g.name as game_name,
                COUNT(i.id) as total,
                COUNT(CASE WHEN i.status != 'pending' THEN 1 END) as reviewed,
                COUNT(CASE WHEN i.status = 'accepted' THEN 1 END) as accepted,
                COUNT(CASE WHEN i.status = 'rejected' THEN 1 END) as rejected,
                COUNT(CASE WHEN i.status = 'flagged' THEN 1 END) as flagged
            FROM games g
            LEFT JOIN images i ON g.id = i.game_id
            WHERE g.id = ?
            GROUP BY g.id, g.name
        """, (game_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Game not found")

        return GameStats(
            game_id=row["game_id"],
            game_name=row["game_name"],
            total=row["total"] or 0,
            reviewed=row["reviewed"] or 0,
            accepted=row["accepted"] or 0,
            rejected=row["rejected"] or 0,
            flagged=row["flagged"] or 0
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stats for game {game_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get game statistics")
