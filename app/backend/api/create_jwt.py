import os
from datetime import timedelta, datetime, timezone

import jwt


SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")  # for jwt token


async def create_access_token(
    user_data: dict,
    expires_delta=None,
) -> dict:
    # jwt токен не зашифровывает данные, которые передаются по интернету
    # но он не дает изменять их без правильной подписи

    to_encode = user_data.copy()  # чтобы не изменить оригинал

    if expires_delta:
        # timezone.utc - стандарт, чтобы не возник конфликт при
        # загрузке кода на сервер, т.к скорее всего там будет идти
        # отсчет от нулевого меридиана (utc)
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datatime.now(timezone.utc) + timedelta(minutes=20)

    to_encode.update({"exp": expire})  # истечение времени ключа
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
