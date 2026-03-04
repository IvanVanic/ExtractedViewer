# VN CG Scan Viewer

A FastAPI-based web viewer for Visual Novel CG scans with image management capabilities.

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python run.py
```

3. Open your browser and navigate to:
```
http://localhost:8000
```

## Project Structure

```
viewer/
├── requirements.txt       # Python package dependencies
├── run.py                # Application entry point
├── main.py               # FastAPI application and routes
├── README.md             # This file
└── static/               # Static assets (CSS, JavaScript)
    └── index.html        # Web interface
```

## Features

- Browse and view Visual Novel CG scans
- Image upload and management
- Fast, responsive web interface
- RESTful API backend

## API Endpoints

The application exposes various endpoints for CG management. See the main.py file for detailed endpoint documentation.
