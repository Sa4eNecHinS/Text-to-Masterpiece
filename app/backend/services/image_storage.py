import asyncio
from pathlib import Path
from uuid import uuid4


def _save(image: bytes, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid4().hex}.jpg"
    path.write_bytes(image)
    return path


def _delete(path: Path) -> None:
    path.unlink(missing_ok=True)


async def save_image(image: bytes, directory: Path) -> Path:
    return await asyncio.to_thread(_save, image, directory)


async def delete_image(path: Path) -> None:
    await asyncio.to_thread(_delete, path)
