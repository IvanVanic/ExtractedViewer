"""Thumbnail generation service for VN CG images."""

import logging
import os
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

_DEFAULT_CLEANED_DIR = Path(__file__).resolve().parent.parent.parent / "cleaned"
CLEANED_DIR = Path(os.environ.get("VN_CG_CLEANED_DIR", str(_DEFAULT_CLEANED_DIR)))
THUMBNAIL_CACHE_DIR = CLEANED_DIR / '.thumbnails'
VALID_SIZES = {200, 800}


def get_thumbnail_path(image_filepath: str, size: int) -> Path:
    """Build path for cached thumbnail without creating it.

    Args:
        image_filepath: Path to original image.
        size: Thumbnail size in pixels (200 or 800).

    Returns:
        Path where thumbnail should be cached.

    Raises:
        ValueError: If size is not 200 or 800.
    """
    if size not in VALID_SIZES:
        raise ValueError(f"Size must be 200 or 800, got {size}")

    image_path = Path(image_filepath)
    relative_path = image_path.relative_to(CLEANED_DIR)

    # Build thumbnail path preserving full relative directory structure
    # This prevents collisions between different games/subdirectories
    # E.g. cleaned/GameA/folder/image.jpg -> .thumbnails/200/GameA/folder/image.jpg
    thumbnail_path = (
        THUMBNAIL_CACHE_DIR
        / str(size)
        / relative_path.parent
        / f"{image_path.stem}.jpg"
    )

    return thumbnail_path


def get_or_create_thumbnail(image_filepath: str, size: int) -> Optional[Path]:
    """Get or create thumbnail for image.

    Args:
        image_filepath: Path to original image.
        size: Thumbnail size in pixels (200 or 800).

    Returns:
        Path to cached thumbnail, or None if generation failed.

    Raises:
        ValueError: If size is not 200 or 800.
    """
    if size not in VALID_SIZES:
        raise ValueError(f"Size must be 200 or 800, got {size}")

    thumbnail_path = get_thumbnail_path(image_filepath, size)

    # Return cached thumbnail if it exists
    if thumbnail_path.exists():
        logger.debug(f"Found cached thumbnail: {thumbnail_path}")
        return thumbnail_path

    try:
        # Create parent directories
        thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

        # Open and process image
        with Image.open(image_filepath) as img:
            # Convert RGBA to RGB with white background
            if img.mode in ('RGBA', 'LA', 'PA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'LA':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Generate thumbnail preserving aspect ratio
            img.thumbnail((size, size), Image.Resampling.LANCZOS)

            # Save as JPEG with quality 85
            img.save(str(thumbnail_path), 'JPEG', quality=85, optimize=True)

        logger.debug(f"Generated thumbnail: {thumbnail_path}")
        return thumbnail_path

    except FileNotFoundError:
        logger.error(
            f"Source image not found: {image_filepath}"
        )
        return None
    except Exception as e:
        logger.error(
            f"Failed to generate thumbnail for {image_filepath} "
            f"(size={size}): {e}"
        )
        return None
