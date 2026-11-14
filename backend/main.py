"""
FastAPI application entry point.

This is the new ASGI app that will gradually replace the Flask app.
Run: uvicorn backend.main:app --reload --port 8000
"""
from fastapi import FastAPI
from backend.routes.api_latest_fastapi import router as api_router


app = FastAPI(
    title="Air Pollution API",
    version="2.0",
    description="Async FastAPI backend for air pollution data",
)

app.include_router(api_router)

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
