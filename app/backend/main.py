import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.fast_api import router
from backend.api.registration import auth_router


app = FastAPI()
app.include_router(router)
app.include_router(auth_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


if __name__ == "__main__":
    logger = logging.getLogger(__name__)
