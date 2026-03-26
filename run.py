#!/usr/bin/env python3
"""
Run script for the Financial Data Extraction application.
This script provides commands to run the backend, frontend, or both.
"""

import sys
import subprocess
import os
import time
import threading
import signal
import uvicorn
from pathlib import Path
from dotenv import load_dotenv

def run_backend():
    """Run the FastAPI backend server."""
    print("🚀 Starting FastAPI backend server...")
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")
    
    # Change to the script's directory to ensure correct paths
    os.chdir(Path(__file__).parent)
    
    print(f"🌐 Application will be available at: http://{host}:{port}")
    
    # Use uvicorn to run the FastAPI app
    # The backend is configured to serve the static frontend files
    uvicorn.run("src.backend:app", host=host, port=port, reload=True)

def install_requirements():
    """Install required packages"""
    print("📦 Installing requirements...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

def main():
    load_dotenv()
    if len(sys.argv) < 2:
        print("Usage: python run.py [command]")
        print("Commands:")
        print("  install   - Install dependencies")
        print("  backend   - Start the FastAPI backend server (serves frontend too)")
        return

    command = sys.argv[1].lower()

    if command == "install":
        install_requirements()
    elif command == "backend":
        run_backend()
    else:
        print(f"Unknown command: {command}")
        print("Available commands: install, backend")

if __name__ == "__main__":
    main()
