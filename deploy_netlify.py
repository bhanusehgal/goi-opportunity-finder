"""Deploy the static web bundle to Netlify via API."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import zipfile

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
API_BASE = "https://api.netlify.com/api/v1"


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": "GoIOpportunityFinder/1.0 (netlify deploy script)",
    }


def _build_zip_bytes(web_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in web_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(web_dir).as_posix())
    return buffer.getvalue()


def _ensure_site(token: str) -> tuple[str, str | None]:
    site_id = os.getenv("NETLIFY_SITE_ID", "").strip()
    if site_id:
        return site_id, None

    payload = {}
    site_name = os.getenv("NETLIFY_SITE_NAME", "").strip()
    if site_name:
        payload["name"] = site_name

    response = requests.post(
        f"{API_BASE}/sites",
        headers={**_auth_headers(token), "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=60,
    )
    response.raise_for_status()
    site = response.json()
    return site["id"], site.get("ssl_url") or site.get("url")


def main() -> int:
    load_dotenv(BASE_DIR / ".env")
    token = os.getenv("NETLIFY_AUTH_TOKEN", "").strip()
    if not token:
        print("NETLIFY_AUTH_TOKEN is required.")
        return 1
    if not WEB_DIR.exists():
        print("web/ directory not found.")
        return 1

    site_id, site_url = _ensure_site(token)
    zip_bytes = _build_zip_bytes(WEB_DIR)
    response = requests.post(
        f"{API_BASE}/sites/{site_id}/deploys",
        headers={**_auth_headers(token), "Content-Type": "application/zip"},
        data=zip_bytes,
        timeout=180,
    )
    response.raise_for_status()
    deploy = response.json()

    final_url = (
        deploy.get("ssl_url")
        or deploy.get("deploy_ssl_url")
        or deploy.get("url")
        or site_url
        or ""
    )
    print(json.dumps({"site_id": site_id, "url": final_url, "state": deploy.get("state")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
