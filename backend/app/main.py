import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, email, geocode, health, order, reservation
from app.core.config import settings
from app.services import menu_cache_service
from app.services.reservation_service import run_reminder_check

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await menu_cache_service.warm()
    await run_reminder_check()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(order.router, prefix="/api/order", tags=["order"])
app.include_router(reservation.router, prefix="/api/reservation", tags=["reservation"])
app.include_router(email.router, prefix="/api/email", tags=["email"])
app.include_router(geocode.router, prefix="/api/geocode", tags=["geocode"])


@app.get("/")
async def root():
    return {"service": settings.app_name, "status": "running"}
