"""Routes for image review and action logging."""

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException

from database import get_db
from models import ReviewAction, UndoRequest, UndoResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["review"])


def _get_session_id(x_session_id: Optional[str] = Header(None)) -> str:
    """Get or generate session ID from header.

    Args:
        x_session_id: Session ID from X-Session-ID header.

    Returns:
        Session ID string (from header or newly generated UUID).
    """
    if x_session_id:
        return x_session_id
    return str(uuid.uuid4())


@router.post("/review")
def review_image(
    review: ReviewAction,
    x_session_id: Optional[str] = Header(None)
) -> dict[str, Any]:
    """Review an image (accept/reject/skip/flag).

    Logs the action to action_log with session ID and updates image status.

    Args:
        review: ReviewAction with image_id, action, and optional rating.
               action: accept/reject/skip/flag
        x_session_id: Optional session ID from header (generates UUID if not provided).

    Returns:
        Dictionary with image_id, new_status, and action_id.

    Raises:
        HTTPException: If image not found, invalid action, or database query fails.
    """
    try:
        if review.action not in ["accept", "reject", "skip", "flag"]:
            raise HTTPException(status_code=400, detail="Invalid action")

        session_id = _get_session_id(x_session_id)

        conn = get_db()
        cursor = conn.cursor()

        # Check if image exists and get current status/rating
        cursor.execute(
            "SELECT status, rating FROM images WHERE id = ?",
            (review.image_id,)
        )
        image_row = cursor.fetchone()

        if not image_row:
            conn.close()
            raise HTTPException(status_code=404, detail="Image not found")

        old_status = image_row["status"]
        old_rating = image_row["rating"]

        # Map action to status
        status_map = {
            "accept": "accepted",
            "reject": "rejected",
            "skip": "skipped",
            "flag": "flagged"
        }
        new_status = status_map[review.action]

        # Update image
        updates = ["status = ?"]
        params = [new_status]

        if review.rating is not None:
            updates.append("rating = ?")
            params.append(review.rating)

        updates.append("reviewed_at = ?")
        params.append(datetime.now().isoformat())

        params.append(review.image_id)

        cursor.execute(
            f"UPDATE images SET {', '.join(updates)} WHERE id = ?",
            params
        )

        # Log action
        cursor.execute("""
            INSERT INTO action_log
            (session_id, image_id, action, old_status, new_status, old_rating, new_rating, undone)
            VALUES (?, ?, ?, ?, ?, ?, ?, FALSE)
        """, (
            session_id,
            review.image_id,
            review.action,
            old_status,
            new_status,
            old_rating,
            review.rating
        ))

        action_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(
            f"Reviewed image {review.image_id}: {old_status} -> {new_status} "
            f"(session: {session_id}, action_id: {action_id})"
        )

        return {
            "image_id": review.image_id,
            "new_status": new_status,
            "action_id": action_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reviewing image {review.image_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to review image")


@router.post("/undo", response_model=UndoResponse)
def undo_actions(
    undo_request: UndoRequest,
    x_session_id: Optional[str] = Header(None)
) -> UndoResponse:
    """Undo the last N review actions for a session.

    Marks actions as undone and reverts image statuses and ratings.

    Args:
        undo_request: UndoRequest with count (1-100) of actions to undo.
        x_session_id: Required session ID from X-Session-ID header.

    Returns:
        UndoResponse with list of undone actions.

    Raises:
        HTTPException: If session ID missing or database query fails.
    """
    try:
        if not x_session_id:
            raise HTTPException(
                status_code=400,
                detail="X-Session-ID header required for undo"
            )

        session_id = x_session_id

        conn = get_db()
        cursor = conn.cursor()

        # Get last N non-undone actions for this session (in reverse chronological order)
        cursor.execute("""
            SELECT
                id,
                image_id,
                action,
                old_status,
                new_status,
                old_rating,
                new_rating
            FROM action_log
            WHERE session_id = ? AND undone = FALSE
            ORDER BY timestamp DESC
            LIMIT ?
        """, (session_id, undo_request.count))

        actions = cursor.fetchall()

        if not actions:
            conn.close()
            return UndoResponse(undone=[])

        undone_list = []

        # Process each action in reverse
        for action_row in actions:
            action_id = action_row["id"]
            image_id = action_row["image_id"]
            old_status = action_row["old_status"]
            old_rating = action_row["old_rating"]

            # Revert image status and rating
            updates = ["status = ?"]
            params = [old_status]

            if old_rating is not None:
                updates.append("rating = ?")
                params.append(old_rating)
            else:
                updates.append("rating = ?")
                params.append(None)

            params.append(image_id)

            cursor.execute(
                f"UPDATE images SET {', '.join(updates)} WHERE id = ?",
                params
            )

            # Mark action as undone
            cursor.execute(
                "UPDATE action_log SET undone = TRUE WHERE id = ?",
                (action_id,)
            )

            undone_list.append({
                "action_id": action_id,
                "image_id": image_id,
                "action": action_row["action"],
                "reverted_status": old_status,
                "reverted_rating": old_rating
            })

        conn.commit()
        conn.close()

        logger.info(
            f"Undone {len(undone_list)} actions for session {session_id}"
        )

        return UndoResponse(undone=undone_list)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error undoing actions for session {x_session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to undo actions")
