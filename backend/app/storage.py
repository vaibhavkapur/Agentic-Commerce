"""Private document storage with tenant-scoped keys and short-lived download URLs.

Keys always start with the organization id, and download URLs are signed and expire quickly.
The API layer additionally checks organization membership before serving a file.
"""

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Protocol

import httpx

from .config import Settings, get_settings


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Storage key escapes the storage root")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()


class SupabaseStorage:
    """Supabase Storage adapter using the service-role key from the backend only.

    Objects are written to a private bucket; the browser never receives the service key. Download
    still flows through the API's signed URL so that membership is checked on every read.
    """

    def __init__(self, url: str, service_key: str, bucket: str):
        self.base = url.rstrip("/") + "/storage/v1"
        self.bucket = bucket
        self.headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        response = httpx.post(
            f"{self.base}/object/{self.bucket}/{key}",
            headers={**self.headers, "Content-Type": content_type, "x-upsert": "false"},
            content=data,
            timeout=30,
        )
        response.raise_for_status()

    def get(self, key: str) -> bytes:
        response = httpx.get(
            f"{self.base}/object/{self.bucket}/{key}", headers=self.headers, timeout=30
        )
        response.raise_for_status()
        return response.content


def build_storage(settings: Settings | None = None) -> Storage:
    settings = settings or get_settings()
    if settings.storage_backend == "supabase":
        if not (settings.supabase_url and settings.supabase_service_role_key):
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        return SupabaseStorage(
            settings.supabase_url, settings.supabase_service_role_key, settings.supabase_storage_bucket
        )
    return LocalStorage(settings.storage_dir)


def document_key(organization_id: str, case_id: str, document_version_id: str, filename: str) -> str:
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._-")[:120] or "document.pdf"
    return f"{organization_id}/{case_id}/{document_version_id}/{safe_name}"


def sign_download(organization_id: str, document_version_id: str, ttl_seconds: int | None = None) -> str:
    settings = get_settings()
    expires = int(time.time()) + (ttl_seconds or settings.storage_signed_url_ttl_seconds)
    payload = json.dumps(
        {"o": organization_id, "d": document_version_id, "e": expires}, separators=(",", ":")
    ).encode()
    signature = hmac.new(settings.auth_jwt_secret.encode(), payload, hashlib.sha256).digest()
    return _b64(payload) + "." + _b64(signature)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def verify_download(token: str) -> tuple[str, str]:
    settings = get_settings()
    try:
        payload_part, signature_part = token.split(".", 1)
        payload, signature = _unb64(payload_part), _unb64(signature_part)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Malformed download token") from exc
    expected = hmac.new(settings.auth_jwt_secret.encode(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid download signature")
    data = json.loads(payload)
    if data["e"] < time.time():
        raise ValueError("Download link expired")
    return data["o"], data["d"]
