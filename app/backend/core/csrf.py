"""Origin-based CSRF protection, independent of proxy Host/forwarded headers."""
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class OriginCSRFMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: list[str]):
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            origins = [value.decode("latin-1") for key, value in scope["headers"] if key.lower() == b"origin"]
            fetch_sites = [value.decode("latin-1") for key, value in scope["headers"] if key.lower() == b"sec-fetch-site"]
            # Require exact configured origins, even if Origin equals Host.
            # A reverse proxy may replace Host; neither it nor client-supplied
            # X-Forwarded-* is a source of trust for browser origins.
            forbidden = (
                len(origins) > 1
                or (bool(origins) and origins[0] not in self.allowed_origins)
                or (not origins and any(site.lower() == "cross-site" for site in fetch_sites))
            )
            if forbidden:
                await JSONResponse({"detail": "Untrusted request origin."}, status_code=403)(scope, receive, send)
                return
            # Preserve existing non-browser/no-Origin clients. This is NOT proof
            # of same-origin: the proxy must preserve Origin and Fetch Metadata.
        await self.app(scope, receive, send)
