"""Start the AI service on SERVICE_HOST:SERVICE_PORT from .env:  python -m app"""
import uvicorn

from app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.service_host, port=settings.service_port)
