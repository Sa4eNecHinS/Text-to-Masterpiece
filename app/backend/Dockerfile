FROM python:3.14-slim

# Копируем менеджер зависимостей uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Не скачиваем другую версию Python.
# Используем Python из базового образа.
ENV UV_PYTHON_DOWNLOADS=0

# Добавляем виртуальное окружение в PATH
ENV PATH="/app/backend/.venv/bin:$PATH"

WORKDIR /app/backend

# Сначала копируем только зависимости
COPY app/backend/pyproject.toml app/backend/uv.lock ./

# Устанавливаем зависимости строго из uv.lock
RUN uv sync --locked --no-dev --no-install-project

# Теперь копируем исходный код
COPY app/backend/ /app/backend/

# Рабочая директория должна содержать пакет backend
WORKDIR /app

EXPOSE 8080

CMD ["uvicorn", "backend.main:app", \
    "--host", "0.0.0.0", "--port", "8080"]
