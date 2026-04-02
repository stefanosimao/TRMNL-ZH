"""
Entry point for the TRMNL-ZH server.
Initializes the FastAPI application and runs the Uvicorn ASGI server.
"""
import uvicorn
from app import create_app

app = create_app()

if __name__ == "__main__":
    # Start the application on the configured host and port
    uvicorn.run("run:app", host="0.0.0.0", port=8000, reload=True)
