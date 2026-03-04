"""Scanner service for indexing VN CG images into database."""

import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


def _get_image_metadata(filepath: Path) -> Optional[dict]:
    """Extract image metadata using Pillow.

    Args:
        filepath: Path to image file.

    Returns:
        Dictionary with width, height, has_alpha, and file_size, or None on error.
    """
    try:
        with Image.open(filepath) as img:
            width, height = img.size
            has_alpha = img.mode in ('RGBA', 'LA', 'PA')

        file_size = filepath.stat().st_size

        return {
            'width': width,
            'height': height,
            'has_alpha': has_alpha,
            'file_size': file_size,
        }
    except Exception as e:
        logger.warning(f"Failed to read metadata for {filepath}: {e}")
        return None


def _scan_image_file(
    db_path: Path,
    game_id: int,
    game_name: str,
    image_filepath: Path,
    cleaned_dir: Path,
) -> Optional[dict]:
    """Scan a single image file and insert into database.

    Args:
        db_path: Path to database file.
        game_id: ID of the game this image belongs to.
        game_name: Name of the game.
        image_filepath: Path to image file.
        cleaned_dir: Path to cleaned directory.

    Returns:
        Dictionary with scan result or None if skipped/failed.
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Calculate filepath relative to cleaned directory
        relative_path = str(image_filepath.relative_to(cleaned_dir)).replace('\\', '/')
        filename = image_filepath.name
        file_format = image_filepath.suffix.lstrip('.').lower()

        # Check if image already exists in database
        cursor.execute(
            'SELECT id FROM images WHERE filepath = ?',
            (relative_path,)
        )
        if cursor.fetchone():
            conn.close()
            return {'action': 'skipped', 'filepath': relative_path}

        # Get image metadata
        metadata = _get_image_metadata(image_filepath)
        if metadata is None:
            conn.close()
            return None

        # Insert image record
        cursor.execute(
            '''INSERT INTO images
               (game_id, filepath, filename, format, width, height, has_alpha, file_size)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                game_id,
                relative_path,
                filename,
                file_format,
                metadata['width'],
                metadata['height'],
                metadata['has_alpha'],
                metadata['file_size'],
            )
        )
        conn.commit()
        conn.close()

        return {'action': 'inserted', 'filepath': relative_path}

    except Exception as e:
        logger.error(f"Error scanning image {image_filepath}: {e}")
        return None


def scan_cleaned_directory(db_path: Path) -> dict:
    """Scan cleaned directory and index games and images into database.

    Args:
        db_path: Path to SQLite database file.

    Returns:
        Dictionary with scan statistics:
        - games_found: Number of game directories found
        - images_found: Total images discovered
        - new_images: Number of new images added to database
        - skipped: Number of images already in database
    """
    db_path = Path(db_path)
    _default = Path(__file__).resolve().parent.parent.parent / "cleaned"
    cleaned_dir = Path(os.environ.get("VN_CG_CLEANED_DIR", str(_default)))

    stats = {
        'games_found': 0,
        'images_found': 0,
        'new_images': 0,
        'skipped': 0,
    }

    if not cleaned_dir.exists():
        logger.error(f"Cleaned directory not found: {cleaned_dir}")
        return stats

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}

    # Iterate through game directories
    for game_dir in cleaned_dir.iterdir():
        if not game_dir.is_dir():
            continue

        game_name = game_dir.name
        logger.info(f"Processing game: {game_name}")

        # Create or get game record
        game_path = str(game_dir).replace('\\', '/')
        cursor.execute(
            'INSERT OR IGNORE INTO games (name, path, image_count) VALUES (?, ?, ?)',
            (game_name, game_path, 0)
        )
        cursor.execute('SELECT id FROM games WHERE name = ?', (game_name,))
        game_id = cursor.fetchone()[0]
        conn.commit()

        stats['games_found'] += 1

        # Collect image files for parallel processing
        image_files = []
        for image_filepath in game_dir.rglob('*'):
            if image_filepath.suffix.lower() in image_extensions:
                image_files.append(image_filepath)

        stats['images_found'] += len(image_files)

        # Process images sequentially (SQLite doesn't handle concurrent writes)
        for image_file in image_files:
            result = _scan_image_file(
                db_path, game_id, game_name, image_file, cleaned_dir
            )
            if result:
                if result['action'] == 'inserted':
                    stats['new_images'] += 1
                elif result['action'] == 'skipped':
                    stats['skipped'] += 1

        # Update game image_count
        cursor.execute(
            'SELECT COUNT(*) FROM images WHERE game_id = ?',
            (game_id,)
        )
        image_count = cursor.fetchone()[0]
        cursor.execute(
            'UPDATE games SET image_count = ? WHERE id = ?',
            (image_count, game_id)
        )
        conn.commit()

        logger.info(
            f"Game '{game_name}': {image_count} images "
            f"({stats['new_images']} new, {stats['skipped']} skipped)"
        )

    conn.close()
    logger.info(f"Scan complete: {stats}")

    return stats
