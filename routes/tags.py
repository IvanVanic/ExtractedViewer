"""Routes for tag management."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

from database import get_db
from models import TagResponse, TagCreate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("/", response_model=list[TagResponse])
def list_tags() -> list[TagResponse]:
    """List all tags with their image counts.

    Returns:
        List of TagResponse objects with tag names, categories, and counts.

    Raises:
        HTTPException: If database query fails.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                t.id,
                t.name,
                t.category,
                COUNT(it.image_id) as count
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            GROUP BY t.id, t.name, t.category
            ORDER BY t.name
        """)

        rows = cursor.fetchall()
        conn.close()

        tags = [
            TagResponse(
                id=row["id"],
                name=row["name"],
                category=row["category"],
                count=row["count"]
            )
            for row in rows
        ]

        return tags
    except Exception as e:
        logger.error(f"Error listing tags: {e}")
        raise HTTPException(status_code=500, detail="Failed to list tags")


@router.post("/", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(tag_create: TagCreate) -> TagResponse:
    """Create a new tag.

    Args:
        tag_create: TagCreate with name and optional category.

    Returns:
        TagResponse with created tag details.

    Raises:
        HTTPException: If tag name already exists or database query fails.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Check if tag already exists
        cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_create.name,))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=409, detail="Tag already exists")

        # Insert new tag
        cursor.execute(
            "INSERT INTO tags (name, category) VALUES (?, ?)",
            (tag_create.name, tag_create.category or "custom")
        )
        conn.commit()

        tag_id = cursor.lastrowid

        # Fetch created tag
        cursor.execute("""
            SELECT
                id,
                name,
                category,
                0 as count
            FROM tags
            WHERE id = ?
        """, (tag_id,))

        row = cursor.fetchone()
        conn.close()

        return TagResponse(
            id=row["id"],
            name=row["name"],
            category=row["category"],
            count=0
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating tag: {e}")
        raise HTTPException(status_code=500, detail="Failed to create tag")


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(tag_id: int) -> None:
    """Delete a tag and all its associations.

    Removes the tag and all image_tags entries referencing it.

    Args:
        tag_id: ID of the tag to delete.

    Raises:
        HTTPException: If tag not found or database query fails.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Check if tag exists
        cursor.execute("SELECT name FROM tags WHERE id = ?", (tag_id,))
        tag_row = cursor.fetchone()

        if not tag_row:
            conn.close()
            raise HTTPException(status_code=404, detail="Tag not found")

        tag_name = tag_row["name"]

        # Delete image_tags associations
        cursor.execute("DELETE FROM image_tags WHERE tag_id = ?", (tag_id,))
        deleted_associations = cursor.rowcount

        # Delete tag
        cursor.execute("DELETE FROM tags WHERE id = ?", (tag_id,))

        conn.commit()
        conn.close()

        logger.info(f"Deleted tag '{tag_name}' (ID: {tag_id}) and {deleted_associations} associations")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting tag {tag_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete tag")
