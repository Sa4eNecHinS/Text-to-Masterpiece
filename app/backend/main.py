import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.fast_api import router
from backend.api.registration import auth_router

"""
INFO:     127.0.0.1:52900 - "POST /Text-to-Masterpiece/generate HTTP/1.1" 200 OK
INFO:     127.0.0.1:35922 - "GET / HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:35922 - "GET /favicon.ico HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:35930 - "GET /auth/ HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:35932 - "GET /docs HTTP/1.1" 200 OK
INFO:     127.0.0.1:35932 - "GET /openapi.json HTTP/1.1" 200 OK
INFO:     127.0.0.1:33270 - "GET / HTTP/1.1" 404 Not Found
INFO:     127.0.0.1:33270 - "GET /docs HTTP/1.1" 200 OK
INFO:     127.0.0.1:33270 - "GET /openapi.json HTTP/1.1" 200 OK
INFO:     127.0.0.1:33270 - "GET /Text-to-Masterpiece HTTP/1.1" 200 OK
INFO:     127.0.0.1:33270 - "GET /Text-to-Masterpiece HTTP/1.1" 200 OK
INFO:     127.0.0.1:33282 - "GET /.well-known/appspecific/com.chrome.devtools.json HTTP/1.1" 404 Not Found
INFO:     Error happend while GETTING user with user_id = string
INFO:     User with user_id - string succefully ADDED
INFO:     127.0.0.1:53166 - "POST /auth/Text-to-Masterpiece/registrate HTTP/1.1" 200 OK
INFO:     Error happend while GETTING user with user_id = 01a05dd8-ecea-75c1-a053-ca8bf6fa1ec9
INFO:     User with user_id - 01a05dd8-ecea-75c1-a053-ca8bf6fa1ec9 succefully ADDED
INFO:     127.0.0.1:36426 - "POST /auth/Text-to-Masterpiece/registrate HTTP/1.1" 200 OK
INFO:     127.0.0.1:47276 - "GET /auth/Text-to-Masterpiece/users/me HTTP/1.1" 401 Unauthorized
INFO:     GET user with user_id = 01a05dd8-ecea-75c1-a053-ca8bf6fa1ec9
INFO:     127.0.0.1:52136 - "POST /auth/Text-to-Masterpiece/token HTTP/1.1" 401 Unauthorized
INFO:     GET user with user_id = 01a05dd8-ecea-75c1-a053-ca8bf6fa1ec9
INFO:     127.0.0.1:56206 - "POST /auth/Text-to-Masterpiece/token HTTP/1.1" 200 OK
INFO:     127.0.0.1:35172 - "GET /auth/Text-to-Masterpiece/users/me HTTP/1.1" 401 Unauthorized
"""

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
