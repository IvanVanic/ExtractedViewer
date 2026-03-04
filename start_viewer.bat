@echo off
title VN CG Viewer
echo ============================================
echo   VN CG Scan Viewer - Starting...
echo ============================================
echo.

cd /d "C:\Users\Ivan\Desktop\VN_CG_Scan\viewer"

echo Starting server on http://localhost:8000
echo Press Ctrl+C to stop the server.
echo.

:: Open browser after 2 second delay
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"

:: Start the server
python -m uvicorn main:app --host 0.0.0.0 --port 8000

pause
