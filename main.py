"""FastAPI application for VN CG Scan viewer."""

import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Add the viewer directory to sys.path for proper imports
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# Configuration constants — driven by environment variables so the app works
# both locally and on Vercel (where Windows absolute paths do not exist).
# Set VN_CG_CLEANED_DIR and VN_CG_DB_PATH in your Vercel project settings.
CLEANED_DIR = Path(os.environ.get("VN_CG_CLEANED_DIR", str(BASE_DIR.resolve().parent / "cleaned")))
DB_PATH = Path(os.environ.get("VN_CG_DB_PATH", str(BASE_DIR / "data.db")))
THUMBNAILS_DIR = CLEANED_DIR / ".thumbnails"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="VN CG Scan Viewer", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve index.html for root path
@app.get("/")
def root():
    """Serve index.html for root path."""
    index_file = BASE_DIR / "static" / "index.html"
    logger.info(f"Serving root path with index.html from {index_file}")
    return FileResponse(path=str(index_file), media_type='text/html')


# Mount static files
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"Static files mounted from {static_dir}")
else:
    logger.warning(f"Static directory not found at {static_dir}")


# Import and include all routers
try:
    from routes import games, images, tags, review, stats
    from database import init_db

    # Include routers
    app.include_router(games.router)
    app.include_router(games.scan_router)
    app.include_router(images.router)
    app.include_router(tags.router)
    app.include_router(review.router)
    app.include_router(stats.router)

    logger.info("All routers included successfully")
except ImportError as e:
    logger.error(f"Failed to import routers or database: {e}")
    raise


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize database on startup."""
    logger.info("Starting up - initializing database")
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
