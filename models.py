"""Pydantic models for VN CG Viewer API request/response."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# Game Models
class GameResponse(BaseModel):
    """Response model for game listing."""

    id: int
    name: str
    image_count: int
    reviewed_count: int
    thumbnail_url: Optional[str] = None

    model_config = {"from_attributes": True}


class GameDetailResponse(GameResponse):
    """Detailed response model for single game."""

    accepted_count: int
    rejected_count: int
    flagged_count: int


# Image Models
class ImageResponse(BaseModel):
    """Response model for image."""

    id: int
    filename: str
    game_id: int
    game_name: str
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    format: Optional[str] = None
    status: str
    rating: Optional[int] = None
    tags: list[str] = Field(default_factory=list)
    thumbnail_url: Optional[str] = None
    preview_url: Optional[str] = None

    model_config = {"from_attributes": True}


class ImageUpdate(BaseModel):
    """Request model for updating image."""

    status: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)
    tags: Optional[list[str]] = None


# Bulk Action Models
class BulkAction(BaseModel):
    """Request model for bulk image actions."""

    image_ids: list[int]
    action: str
    tag: Optional[str] = None


class ReviewAction(BaseModel):
    """Request model for review action on single image."""

    image_id: int
    action: str
    rating: Optional[int] = Field(None, ge=1, le=5)


# Undo Models
class UndoRequest(BaseModel):
    """Request model for undo action."""

    count: int = Field(1, ge=1, le=100)


class UndoResponse(BaseModel):
    """Response model for undo action."""

    undone: list[dict[str, Any]]


# Statistics Models
class GameStats(BaseModel):
    """Statistics for a single game."""

    game_id: int
    game_name: str
    total: int
    reviewed: int
    accepted: int
    rejected: int
    flagged: int


class StatsResponse(BaseModel):
    """Response model for statistics."""

    total_images: int
    reviewed: int
    accepted: int
    rejected: int
    flagged: int
    by_game: list[GameStats]


# Tag Models
class TagResponse(BaseModel):
    """Response model for tag."""

    id: int
    name: str
    category: str
    count: int

    model_config = {"from_attributes": True}


class TagCreate(BaseModel):
    """Request model for creating tag."""

    name: str = Field(..., min_length=1, max_length=50)
    category: Optional[str] = Field("custom", max_length=50)


# Pagination Model
class PaginatedResponse(BaseModel):
    """Generic paginated response model."""

    items: list[Any]
    total: int
    page: int
    per_page: int
    pages: int
