"""Isolated ORM/API tests: SQLite stands in for PostgreSQL; no real API calls."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from io import BytesIO

# Set before app imports; never use credentials or a database from the local .env.
os.environ.update(
    SECRET_KEY="test-only-secret-key-at-least-32-bytes", ALGORITHM="HS256",
    COOKIE_SECURE="false", COOKIE_SAMESITE="lax", ACCESS_TOKEN_EXPIRE_MINUTES="20",
    DB_DRIVER="postgresql+asyncpg", DB_USER="test", DB_PASS="test",
    DB_HOST="127.0.0.1", DB_PORT="5432", DB_NAME="test", DB_SSL="",
    DB_POOL_SIZE="7", DB_MAX_OVERFLOW="6", DB_POOL_TIMEOUT="10",
    CLOUDFLARE_ACCOUNT_ID="test-account", CLOUDFLARE_API_TOKEN="test-token",
    AI_DAILY_NEURON_LIMIT="9000", AI_NEURON_COST_FLUX_1_SCHNELL="65",
    AI_NEURON_COST_FLUX_2_KLEIN_4B="110", AI_MAX_CONCURRENT_GENERATIONS="5",
    RATE_LIMIT_USER_CAPACITY="1", RATE_LIMIT_USER_REFILL_SECONDS="7",
    RATE_LIMIT_IP_CAPACITY="5", RATE_LIMIT_IP_REFILL_PER_MINUTE="45",
    B2_ENDPOINT="https://s3.example.invalid", B2_REGION="test-region",
    B2_BUCKET_NAME="test-images", B2_KEY_ID="test-key-id", B2_APPLICATION_KEY="test-key",
)

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from backend.api import images
from backend.database.dependencies import get_db
from backend.database.models import Base, Model
from backend.main import app
from backend.services import image_generation
from backend.services.image_storage import S3ImageStorage

# Preserve the real class when the provider's client factory is mocked.
AsyncClient = httpx.AsyncClient


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.connection.create_function("char_length", 1, len)
        connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS tests")
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(connection)
        connection.commit()
        with Session(connection, expire_on_commit=False) as session:
            session.add_all([
                Model(model_id="cloudflare/flux-1-schnell", name="FLUX.1-schnell",
                      provider="cloudflare", provider_model_id="@cf/black-forest-labs/flux-1-schnell"),
                Model(model_id="cloudflare/flux-2-klein-4b", name="FLUX-2-klein-4b",
                      provider="cloudflare", provider_model_id="@cf/black-forest-labs/flux-2-klein-4b"),
            ])
            session.commit()

            @asynccontextmanager
            async def begin():
                with session.begin():
                    yield

            yield SimpleNamespace(
                add=session.add, execute=AsyncMock(side_effect=session.execute),
                get=AsyncMock(side_effect=session.get), flush=AsyncMock(side_effect=session.flush),
                commit=AsyncMock(side_effect=session.commit), rollback=AsyncMock(side_effect=session.rollback),
                begin=begin, sync=session,
            )
    engine.dispose()


@pytest.fixture
def storage():
    objects, bodies = {}, []
    def put(**options):
        assert options["IfNoneMatch"] == "*"
        assert options["Key"] not in objects
        objects[options["Key"]] = (options["Body"], options["ContentType"])
        return {}
    def get(**options):
        from botocore.exceptions import ClientError
        if options["Key"] not in objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        data, content_type = objects[options["Key"]]
        body = BytesIO(data)
        bodies.append(body)
        return {"Body": body, "ContentType": content_type, "ContentLength": len(data)}
    sdk = SimpleNamespace(
        put_object=Mock(side_effect=put), get_object=Mock(side_effect=get),
        delete_object=Mock(side_effect=lambda **options: objects.pop(options["Key"], None)),
        close=Mock(),
    )
    store = S3ImageStorage(sdk, "test-images")
    store.objects, store.bodies = objects, bodies
    store.upload = AsyncMock(wraps=store.upload)
    store.download = AsyncMock(wraps=store.download)
    store.delete = AsyncMock(wraps=store.delete)
    return store


@pytest_asyncio.fixture
async def client(db, storage, monkeypatch):
    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[images.get_storage] = lambda: storage
    # Existing SQLite tests isolate the reservation boundary. PostgreSQL tests
    # replace this with the real implementation against a disposable schema.
    monkeypatch.setattr(images, "reserve_generation_neurons", AsyncMock())

    @asynccontextmanager
    async def unlocked(*args, **kwargs):
        yield SimpleNamespace(check_connection=AsyncMock())

    # SQLite cannot implement PostgreSQL session locks. Dedicated unit and
    # PostgreSQL integration tests exercise the actual lock component.
    monkeypatch.setattr(images, "generation_lock", unlocked)
    monkeypatch.setattr(images, "check_generation_rate_limit", AsyncMock(
        side_effect=lambda ip_address, user_id, guest_uuid, response: guest_uuid
    ))
    async with AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def provider(monkeypatch):
    def install(handler):
        requests = []

        def tracked(request):
            requests.append(request)
            return handler(request)

        monkeypatch.setattr(image_generation.httpx, "AsyncClient", lambda **kwargs: AsyncClient(
            transport=httpx.MockTransport(tracked), **kwargs
        ))
        return requests

    return install


@pytest.fixture(scope="session")
def budget_postgres_url():
    """Shared disposable PostgreSQL cluster; never use application DB settings."""
    explicit = os.getenv("TEST_AI_DATABASE_URL")
    if explicit:
        yield explicit
        return
    if os.geteuid() == 0 or not all(shutil.which(cmd) for cmd in ("initdb", "pg_ctl")):
        pytest.skip("Install PostgreSQL binaries or set TEST_AI_DATABASE_URL for isolated schema tests")

    with tempfile.TemporaryDirectory(prefix="t2m-pg-") as directory:
        root = Path(directory)
        data = root / "data"
        def run(*args):
            return subprocess.run(args, check=True, capture_output=True, text=True, timeout=60)
        run("initdb", "-D", str(data), "-U", "t2m_test", "--auth=trust", "--no-locale", "--encoding=UTF8")
        run("pg_ctl", "-D", str(data), "-l", str(root / "server.log"), "-w", "start",
            "-o", f"-F -h '' -k {root} -p 5432")
        try:
            yield URL.create("postgresql+asyncpg", username="t2m_test", database="postgres",
                             query={"host": str(root), "port": "5432"})
        finally:
            run("pg_ctl", "-D", str(data), "-m", "immediate", "-w", "stop")
