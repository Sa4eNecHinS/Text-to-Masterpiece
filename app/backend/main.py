from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from backend.api.auth import auth_router
from backend.api.images import router as images_router
from backend.api.site import router as site_router
from backend.core.config import settings
from backend.services.image_storage import close_image_storage, get_image_storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Construct one SDK client per worker, outside the event loop; no B2 request
    # is made by client creation. Other routes remain usable without B2 keys.
    if settings.B2_KEY_ID and settings.B2_APPLICATION_KEY:
        await run_in_threadpool(get_image_storage)
    try:
        yield
    finally:
        await close_image_storage()


app = FastAPI(lifespan=lifespan)
app.include_router(images_router)
app.include_router(auth_router)
app.include_router(site_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
