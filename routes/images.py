"""Routes for image retrieval, viewing, and management."""

import logging
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from database import get_db
from models import ImageResponse, ImageUpdate, BulkAction, PaginatedResponse
from services.thumbnails import get_or_create_thumbnail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/images", tags=["images"])

# Resolved from environment variable — set VN_CG_CLEANED_DIR in Vercel project settings.
_DEFAULT_CLEANED_DIR = Path(__file__).resolve().parent.parent.parent / "cleaned"
CLEANED_DIR = Path(os.environ.get("VN_CG_CLEANED_DIR", str(_DEFAULT_CLEANED_DIR)))


def _build_image_response(row: Any, conn: Any) -> ImageResponse:
    """Build ImageResponse from database row with tags.

    Args:
        row: Database row with image data.
        conn: Database connection for fetching tags.

    Returns:
        ImageResponse object with all metadata and tags.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.name
        FROM tags t
        JOIN image_tags it ON t.id = it.tag_id
        WHERE it.image_id = ?
    """, (row["id"],))

    tags = [tag_row["name"] for tag_row in cursor.fetchall()]

    return ImageResponse(
        id=row["id"],
        filename=row["filename"],
        game_id=row["game_id"],
        game_name=row["game_name"],
        width=row["width"],
        height=row["height"],
        file_size=row["file_size"],
        format=row["format"],
        status=row["status"],
        rating=row["rating"],
        tags=tags,
        thumbnail_url=f"/api/images/{row['id']}/thumbnail",
        preview_url=f"/api/images/{row['id']}/preview"
    )


@router.get("/", response_model=PaginatedResponse)
def list_images(
    game_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: str = Query("filename"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
) -> PaginatedResponse:
    """List images with filtering and pagination.

    Args:
        game_id: Filter by game ID.
        status: Filter by image status (pending/accepted/rejected/flagged/skipped).
            When omitted or empty, rejected images are excluded by default.
        tag: Filter by tag name.
        search: Search in filename (LIKE).
        sort: Sort field (filename/file_size/status/rating).
        page: Page number (1-indexed).
        per_page: Items per page (default 50, max 500).

    Returns:
        PaginatedResponse with paginated image list and metadata.

    Raises:
        HTTPException: If database query fails or invalid parameters.
    """
    try:
        if sort not in ["filename", "file_size", "status", "rating"]:
            raise HTTPException(status_code=400, detail="Invalid sort field")

        conn = get_db()
        cursor = conn.cursor()

        # Build WHERE clause dynamically
        where_clauses = ["1=1"]
        params: list[Any] = []

        # Convert empty strings to None for proper filtering
        if game_id is not None:
            where_clauses.append("i.game_id = ?")
            params.append(game_id)

        # Only add status filter if status is not None and not empty string.
        # When no status is provided (i.e. "All Status" in the UI), rejected
        # images are excluded by default so they do not clutter the main view.
        # Users can still see rejected images by explicitly selecting "Rejected".
        if status is not None and status != "":
            where_clauses.append("i.status = ?")
            params.append(status)
        else:
            where_clauses.append("i.status != 'rejected'")

        # Only add search filter if search is not None and not empty string
        if search is not None and search != "":
            where_clauses.append("i.filename LIKE ?")
            params.append(f"%{search}%")

        where_clause = " AND ".join(where_clauses)

        # Handle tag filter with JOIN (only if tag is not None and not empty string)
        if tag is not None and tag != "":
            count_query = f"""
                SELECT COUNT(DISTINCT i.id) as total
                FROM images i
                JOIN image_tags it ON i.id = it.image_id
                JOIN tags t ON it.tag_id = t.id
                JOIN games g ON i.game_id = g.id
                WHERE {where_clause} AND t.name = ?
            """
            params_count = params + [tag]

            list_query = f"""
                SELECT DISTINCT
                    i.id,
                    i.filename,
                    i.game_id,
                    g.name as game_name,
                    i.width,
                    i.height,
                    i.file_size,
                    i.format,
                    i.status,
                    i.rating
                FROM images i
                JOIN image_tags it ON i.id = it.image_id
                JOIN tags t ON it.tag_id = t.id
                JOIN games g ON i.game_id = g.id
                WHERE {where_clause} AND t.name = ?
                ORDER BY i.{sort}
                LIMIT ? OFFSET ?
            """
            params_list = params + [tag]
        else:
            count_query = f"""
                SELECT COUNT(*) as total
                FROM images i
                JOIN games g ON i.game_id = g.id
                WHERE {where_clause}
            """
            params_count = params

            list_query = f"""
                SELECT
                    i.id,
                    i.filename,
                    i.game_id,
                    g.name as game_name,
                    i.width,
                    i.height,
                    i.file_size,
                    i.format,
                    i.status,
                    i.rating
                FROM images i
                JOIN games g ON i.game_id = g.id
                WHERE {where_clause}
                ORDER BY i.{sort}
                LIMIT ? OFFSET ?
            """
            params_list = params

        # Get total count
        cursor.execute(count_query, params_count)
        total = cursor.fetchone()["total"]

        # Calculate pagination
        pages = (total + per_page - 1) // per_page
        offset = (page - 1) * per_page

        if page > pages and pages > 0:
            raise HTTPException(status_code=400, detail="Page out of range")

        # Get paginated results
        params_list.extend([per_page, offset])
        cursor.execute(list_query, params_list)
        rows = cursor.fetchall()

        images = [_build_image_response(row, conn) for row in rows]
        conn.close()

        return PaginatedResponse(
            items=images,
            total=total,
            page=page,
            per_page=per_page,
            pages=pages
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing images: {e}")
        raise HTTPException(status_code=500, detail="Failed to list images")


@router.get("/{image_id}", response_model=ImageResponse)
def get_image(image_id: int) -> ImageResponse:
    """Get detailed information about a specific image.

    Args:
        image_id: ID of the image.

    Returns:
        ImageResponse with full metadata and tags.

    Raises:
        HTTPException: If image not found or database query fails.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                i.id,
                i.filename,
                i.game_id,
                g.name as game_name,
                i.width,
                i.height,
                i.file_size,
                i.format,
                i.status,
                i.rating
            FROM images i
            JOIN games g ON i.game_id = g.id
            WHERE i.id = ?
        """, (image_id,))

        row = cursor.fetchone()

        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Image not found")

        response = _build_image_response(row, conn)
        conn.close()

        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting image {image_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get image")


@router.patch("/{image_id}", response_model=ImageResponse)
def update_image(image_id: int, update: ImageUpdate) -> ImageResponse:
    """Update image status, rating, and tags.

    Args:
        image_id: ID of the image to update.
        update: ImageUpdate with status, rating, and/or tags.

    Returns:
        Updated ImageResponse.

    Raises:
        HTTPException: If image not found or database query fails.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Check image exists
        cursor.execute("SELECT id FROM images WHERE id = ?", (image_id,))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Image not found")

        # Update status and rating
        if update.status is not None or update.rating is not None:
            updates = []
            params = []

            if update.status is not None:
                updates.append("status = ?")
                params.append(update.status)

            if update.rating is not None:
                updates.append("rating = ?")
                params.append(update.rating)

            if updates:
                params.append(image_id)
                cursor.execute(
                    f"UPDATE images SET {', '.join(updates)} WHERE id = ?",
                    params
                )
                conn.commit()

        # Update tags if provided
        if update.tags is not None:
            # Clear existing tags
            cursor.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))

            # Add new tags
            for tag_name in update.tags:
                cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                tag_row = cursor.fetchone()

                if tag_row:
                    cursor.execute(
                        "INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                        (image_id, tag_row["id"])
                    )

            conn.commit()

        # Fetch updated image
        cursor.execute("""
            SELECT
                i.id,
                i.filename,
                i.game_id,
                g.name as game_name,
                i.width,
                i.height,
                i.file_size,
                i.format,
                i.status,
                i.rating
            FROM images i
            JOIN games g ON i.game_id = g.id
            WHERE i.id = ?
        """, (image_id,))

        row = cursor.fetchone()
        response = _build_image_response(row, conn)
        conn.close()

        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating image {image_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update image")


@router.post("/bulk")
def bulk_action(action_request: BulkAction) -> dict[str, Any]:
    """Perform bulk action on multiple images.

    Args:
        action_request: BulkAction with image_ids, action, and optional tag.
                       action: accept/reject/flag/tag

    Returns:
        Dictionary with updated count and action details.

    Raises:
        HTTPException: If action invalid or database query fails.
    """
    try:
        if not action_request.image_ids:
            raise HTTPException(status_code=400, detail="No image IDs provided")

        if action_request.action not in ["accept", "reject", "flag", "tag"]:
            raise HTTPException(status_code=400, detail="Invalid action")

        if action_request.action == "tag" and not action_request.tag:
            raise HTTPException(status_code=400, detail="Tag required for tag action")

        conn = get_db()
        cursor = conn.cursor()

        updated_count = 0

        if action_request.action in ["accept", "reject", "flag"]:
            status_map = {
                "accept": "accepted",
                "reject": "rejected",
                "flag": "flagged"
            }
            new_status = status_map[action_request.action]

            placeholders = ",".join("?" * len(action_request.image_ids))
            cursor.execute(
                f"UPDATE images SET status = ? WHERE id IN ({placeholders})",
                [new_status] + action_request.image_ids
            )
            updated_count = cursor.rowcount

        elif action_request.action == "tag":
            # Get or create tag
            cursor.execute("SELECT id FROM tags WHERE name = ?", (action_request.tag,))
            tag_row = cursor.fetchone()

            if not tag_row:
                cursor.execute(
                    "INSERT INTO tags (name, category) VALUES (?, ?)",
                    (action_request.tag, "custom")
                )
                tag_id = cursor.lastrowid
            else:
                tag_id = tag_row["id"]

            # Add tag to all images
            for image_id in action_request.image_ids:
                cursor.execute(
                    "INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                    (image_id, tag_id)
                )

            updated_count = len(action_request.image_ids)

        conn.commit()
        conn.close()

        logger.info(f"Bulk action {action_request.action} completed on {updated_count} images")

        return {
            "action": action_request.action,
            "updated_count": updated_count
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk action: {e}")
        raise HTTPException(status_code=500, detail="Bulk action failed")


@router.delete("/purge-rejected")
def purge_rejected_images(
    game_id: Optional[int] = Query(None),
) -> dict[str, Any]:
    """Permanently delete all rejected images and their associated data.

    Removes rejected image files from disk (including both thumbnail sizes),
    then deletes all related database records (image_tags, action_log, images)
    and recalculates each affected game's image_count.

    Args:
        game_id: Optional game ID to scope deletion to a single game.
                 When omitted, all rejected images across every game are purged.

    Returns:
        Dictionary with ``deleted_count`` indicating how many images were removed.

    Raises:
        HTTPException: If the database query or file removal encounters an
                       unrecoverable error.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        # ------------------------------------------------------------------
        # 1. Collect rejected images (id, game_id, filepath)
        # ------------------------------------------------------------------
        if game_id is not None:
            cursor.execute(
                "SELECT id, game_id, filepath FROM images WHERE status = 'rejected' AND game_id = ?",
                (game_id,),
            )
        else:
            cursor.execute(
                "SELECT id, game_id, filepath FROM images WHERE status = 'rejected'"
            )

        rows = cursor.fetchall()

        if not rows:
            conn.close()
            return {"deleted_count": 0}

        image_ids: list[int] = [row["id"] for row in rows]
        affected_game_ids: set[int] = {row["game_id"] for row in rows}

        # ------------------------------------------------------------------
        # 2. Delete files from disk
        # ------------------------------------------------------------------
        for row in rows:
            filepath: str = row["filepath"]

            # Original file
            original_path = CLEANED_DIR / filepath
            if original_path.exists():
                try:
                    original_path.unlink()
                except OSError as exc:
                    logger.warning(f"Could not delete file {original_path}: {exc}")

            # Thumbnails: .thumbnails/<size>/<relative_dir>/<stem>.jpg
            rel = Path(filepath)
            for thumb_size in ("200", "800", "128", "512"):
                thumb_path = (
                    CLEANED_DIR / ".thumbnails" / thumb_size / rel.parent / f"{rel.stem}.jpg"
                )
                if thumb_path.exists():
                    try:
                        thumb_path.unlink()
                    except OSError as exc:
                        logger.warning(f"Could not delete thumbnail {thumb_path}: {exc}")

        # ------------------------------------------------------------------
        # 3. Delete associated DB records
        # ------------------------------------------------------------------
        placeholders = ",".join("?" * len(image_ids))

        cursor.execute(
            f"DELETE FROM image_tags WHERE image_id IN ({placeholders})",
            image_ids,
        )

        cursor.execute(
            f"DELETE FROM action_log WHERE image_id IN ({placeholders})",
            image_ids,
        )

        cursor.execute(
            f"DELETE FROM images WHERE id IN ({placeholders})",
            image_ids,
        )

        # ------------------------------------------------------------------
        # 4. Recompute image_count for every affected game
        # ------------------------------------------------------------------
        for gid in affected_game_ids:
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM images WHERE game_id = ?",
                (gid,),
            )
            count_row = cursor.fetchone()
            new_count = count_row["cnt"] if count_row else 0
            cursor.execute(
                "UPDATE games SET image_count = ? WHERE id = ?",
                (new_count, gid),
            )

        conn.commit()
        conn.close()

        deleted_count = len(image_ids)
        logger.info(
            f"purge-rejected: permanently deleted {deleted_count} image(s) "
            f"(game_id filter={game_id!r})"
        )

        return {"deleted_count": deleted_count}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error purging rejected images: {e}")
        raise HTTPException(status_code=500, detail="Failed to purge rejected images")


@router.get("/{image_id}/file")
def get_image_file(image_id: int) -> FileResponse:
    """Serve original image file.

    Args:
        image_id: ID of the image.

    Returns:
        FileResponse with original image file.

    Raises:
        HTTPException: If image not found or file not accessible.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT filepath FROM images WHERE id = ?", (image_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Image not found")

        file_path = CLEANED_DIR / row["filepath"]

        if not file_path.exists():
            logger.error(f"Image file not found: {file_path}")
            raise HTTPException(status_code=404, detail="Image file not found")

        return FileResponse(str(file_path), media_type="image/jpeg")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving image {image_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to serve image")


@router.get("/{image_id}/thumbnail")
def get_thumbnail(image_id: int) -> FileResponse:
    """Serve 200px thumbnail image.

    Generates thumbnail on demand if not cached.

    Args:
        image_id: ID of the image.

    Returns:
        FileResponse with 200px thumbnail.

    Raises:
        HTTPException: If image not found or thumbnail generation fails.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT filepath FROM images WHERE id = ?", (image_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Image not found")

        file_path = CLEANED_DIR / row["filepath"]

        if not file_path.exists():
            logger.error(f"Image file not found: {file_path}")
            raise HTTPException(status_code=404, detail="Image file not found")

        thumbnail_path = get_or_create_thumbnail(str(file_path), 200)

        if not thumbnail_path:
            raise HTTPException(status_code=500, detail="Thumbnail generation failed")

        return FileResponse(str(thumbnail_path), media_type="image/jpeg")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving thumbnail for {image_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to serve thumbnail")


@router.get("/{image_id}/preview")
def get_preview(image_id: int) -> FileResponse:
    """Serve 800px preview image.

    Generates preview on demand if not cached.

    Args:
        image_id: ID of the image.

    Returns:
        FileResponse with 800px preview.

    Raises:
        HTTPException: If image not found or preview generation fails.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT filepath FROM images WHERE id = ?", (image_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Image not found")

        file_path = CLEANED_DIR / row["filepath"]

        if not file_path.exists():
            logger.error(f"Image file not found: {file_path}")
            raise HTTPException(status_code=404, detail="Image file not found")

        preview_path = get_or_create_thumbnail(str(file_path), 800)

        if not preview_path:
            raise HTTPException(status_code=500, detail="Preview generation failed")

        return FileResponse(str(preview_path), media_type="image/jpeg")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving preview for {image_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to serve preview")
