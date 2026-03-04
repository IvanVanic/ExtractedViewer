#!/usr/bin/env python
"""Test script to run the server and validate routes."""

import subprocess
import time
import urllib.request
import signal
import os

def main():
    # Start the server
    print("Starting FastAPI server...")
    server_process = subprocess.Popen(
        ["python", "-c", "import uvicorn; uvicorn.run('main:app', host='127.0.0.1', port=8706)"],
        cwd="C:/Users/Ivan/Desktop/VN_CG_Scan/viewer"
    )

    try:
        # Wait for server to start
        print("Waiting 5 seconds for server to start...")
        time.sleep(5)

        # Run tests
        tests = [
            ('/', 'text/html', 'VN CG Viewer'),
            ('/static/style.css', 'text/css', 'root'),
            ('/static/app.js', 'application/javascript', 'AppState'),
            ('/static/manifest.json', 'application/json', 'VN CG'),
        ]

        print("\nRunning tests...")
        for path, expected_ct, expected_content in tests:
            try:
                resp = urllib.request.urlopen(f'http://127.0.0.1:8706{path}')
                body = resp.read().decode('utf-8', errors='replace')
                ct = resp.headers.get('content-type', '')
                has_content = expected_content in body
                status = 'PASS' if has_content else 'FAIL'
                print(f'{path}: status={resp.status} ct_ok={expected_ct in ct} content_ok={has_content} -> {status}')
            except Exception as e:
                print(f'{path}: FAIL - {e}')

    finally:
        # Kill the server
        print("\nKilling server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        print("Server stopped")

if __name__ == "__main__":
    main()
