import bcrypt


async def hash_password(password: str) -> str:
    # 1. Превращаем строку в байты
    pwd_bytes = password.encode("utf-8")
    # 2. Генерируем соль
    salt = bcrypt.gensalt()
    # 3. Хешируем
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    # 4. Декодируем байты хеша обратно в строку для хранения в БД
    return hashed_password.decode("utf-8")


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    # 1. Превращаем пароль и сохраненный хеш в байты
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    # 2. Сравниваем (библиотека сама достанет соль из хеша)
    return bcrypt.checkpw(password_bytes, hashed_bytes)
