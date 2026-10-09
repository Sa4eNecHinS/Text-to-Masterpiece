from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.api.auth import auth_router
from backend.api.images import router as images_router
from backend.api.site import router as site_router
from backend.core.config import IMAGE_STORAGE_PATH

app = FastAPI()
app.include_router(images_router)
app.include_router(auth_router)
app.include_router(site_router)
app.mount(
    "/images", StaticFiles(directory=IMAGE_STORAGE_PATH, check_dir=False), name="images"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
