import base64
import binascii

import httpx


def is_supported_model(model_id: str, provider: str, provider_model_id: str) -> bool:
    if provider != "cloudflare":
        return False
    if model_id == "cloudflare/flux-1-schnell":
        return provider_model_id == "@cf/black-forest-labs/flux-1-schnell"
    if model_id == "cloudflare/flux-2-klein-4b":
        return provider_model_id == "@cf/black-forest-labs/flux-2-klein-4b"
    return False


class ImageGenerationError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        provider_codes: tuple[int, ...] = (),
    ) -> None:
        self.status_code = status_code
        self.provider_codes = provider_codes
        diagnostics = []
        if status_code is not None:
            diagnostics.append(f"HTTP {status_code}")
        if provider_codes:
            diagnostics.append(
                "Cloudflare codes: " + ", ".join(map(str, provider_codes))
            )
        if diagnostics:
            message = f"{message} ({'; '.join(diagnostics)})"
        super().__init__(message)


def _provider_codes(payload: object) -> tuple[int, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("errors"), list):
        return ()
    return tuple(
        error["code"]
        for error in payload["errors"]
        if isinstance(error, dict) and type(error.get("code")) is int
    )


def _request_options(prompt: str, model: str) -> dict:
    if model == "@cf/black-forest-labs/flux-1-schnell":
        return {"json": {"prompt": prompt, "steps": 4}}
    if model == "@cf/black-forest-labs/flux-2-klein-4b":
        # files forces multipart even for text-only inputs; httpx supplies boundary.
        return {"files": {"prompt": (None, prompt)}}
    raise ImageGenerationError("Unsupported image generation model.")


async def generate_image(
    prompt: str, account_id: str, api_token: str, model: str
) -> bytes:
    options = _request_options(prompt, model)
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_token}"},
                **options,
            )
    except httpx.TimeoutException as error:
        raise ImageGenerationError(
            "Image generation timed out. Please try again."
        ) from error
    except httpx.HTTPError as error:
        raise ImageGenerationError(
            "Image generation provider is unavailable."
        ) from error

    try:
        payload = response.json()
    except ValueError as error:
        message = (
            "Image generation provider returned an invalid response."
            if response.is_success
            else "Image generation provider returned an error."
        )
        raise ImageGenerationError(message, status_code=response.status_code) from error

    if not response.is_success:
        raise ImageGenerationError(
            "Image generation provider returned an error.",
            status_code=response.status_code,
            provider_codes=_provider_codes(payload),
        )

    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ImageGenerationError(
            "Image generation provider reported a failure.",
            status_code=response.status_code,
            provider_codes=_provider_codes(payload),
        )

    result = payload.get("result")
    encoded = result.get("image") if isinstance(result, dict) else None

    if not isinstance(encoded, str) or not encoded:
        raise ImageGenerationError("Image generation provider returned no image.")

    try:
        image = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ImageGenerationError(
            "Image generation provider returned invalid image data."
        ) from error

    if not image:
        raise ImageGenerationError("Image generation provider returned an empty image.")

    return image
