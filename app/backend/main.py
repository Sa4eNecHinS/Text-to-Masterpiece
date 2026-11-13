from contextlib import asynccontextmanager

from backend.api.auth import auth_router
from backend.api.images import router as images_router
from backend.api.site import router as site_router
from backend.core.config import settings
from backend.core.csrf import OriginCSRFMiddleware
from backend.services.image_storage import close_image_storage, get_image_storage
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool


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
# CORS is outermost so allowed browser origins can read CSRF error responses.
app.add_middleware(OriginCSRFMiddleware, allowed_origins=settings.CORS_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
