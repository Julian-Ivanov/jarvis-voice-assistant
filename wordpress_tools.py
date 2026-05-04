"""
wordpress_tools.py — Multi-site WordPress manager for Jarvis.

Credentials are cached in ~/.jarvis/wp-sites.json (mode 0600) using this schema:

    {
        "example.com": {
            "base_url": "https://example.com",
            "user": "admin",
            "app_password": "xxxx xxxx xxxx xxxx",
            "has_woocommerce": true
        }
    }

Authentication uses WordPress Application Passwords transmitted as HTTP Basic
Auth (base64-encoded "user:app_password"). Application Passwords also work on
WooCommerce REST routes (/wp-json/wc/v3/). App passwords are never logged or
printed. Cache writes are atomic (tmp file + os.replace) to avoid corruption.
"""

import base64
import json
import mimetypes
import os
import pathlib
import tempfile
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

_CACHE_DIR = pathlib.Path.home() / ".jarvis"
_CACHE_FILE = _CACHE_DIR / "wp-sites.json"
_TIMEOUT = 30.0


def _load_cache() -> dict[str, dict]:
    if not _CACHE_FILE.exists():
        return {}
    with _CACHE_FILE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _save_cache(data: dict[str, dict]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=_CACHE_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp_path, _CACHE_FILE)
        os.chmod(_CACHE_FILE, 0o600)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _get_site(domain: str) -> dict:
    cache = _load_cache()
    if domain not in cache:
        raise RuntimeError(f"WordPress site '{domain}' not registered")
    return cache[domain]


def _auth_header(site: dict) -> str:
    token = base64.b64encode(
        f"{site['user']}:{site['app_password']}".encode()
    ).decode()
    return f"Basic {token}"


def _client(site: dict) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"Authorization": _auth_header(site)},
        timeout=_TIMEOUT,
    )


# ---------------------------------------------------------------------------
# Site registry (synchronous — no I/O wait needed)
# ---------------------------------------------------------------------------


def list_sites() -> list[str]:
    """Return all registered domain names."""
    return list(_load_cache().keys())


def add_site(
    domain: str,
    base_url: str,
    user: str,
    app_password: str,
    has_woocommerce: bool = False,
) -> None:
    """Register (or overwrite) a WordPress site in the local cache."""
    cache = _load_cache()
    cache[domain] = {
        "base_url": base_url.rstrip("/"),
        "user": user,
        "app_password": app_password,
        "has_woocommerce": bool(has_woocommerce),
    }
    _save_cache(cache)


def remove_site(domain: str) -> None:
    """Remove a site from the local cache."""
    cache = _load_cache()
    if domain not in cache:
        raise RuntimeError(f"WordPress site '{domain}' not registered")
    del cache[domain]
    _save_cache(cache)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


async def test_connection(domain: str) -> dict:
    """GET /wp-json/ and return {"name": str, "version": str}."""
    site = _get_site(domain)
    async with _client(site) as http:
        r = await http.get(f"{site['base_url']}/wp-json/")
        r.raise_for_status()
    data = r.json()
    return {
        "name": data.get("name", ""),
        "version": data.get("namespaces", []) and data.get("generator", ""),
        "url": data.get("url", site["base_url"]),
    }


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------


def _clean_post(raw: dict) -> dict:
    return {
        "id": raw.get("id"),
        "title": raw.get("title", {}).get("rendered", ""),
        "status": raw.get("status"),
        "link": raw.get("link"),
        "date": raw.get("date"),
        "modified": raw.get("modified"),
        "slug": raw.get("slug"),
    }


async def list_posts(
    domain: str, status: str = "any", limit: int = 10
) -> list[dict]:
    """Return up to *limit* posts filtered by *status*."""
    site = _get_site(domain)
    params: dict[str, Any] = {"per_page": min(limit, 100), "status": status}
    async with _client(site) as http:
        r = await http.get(f"{site['base_url']}/wp-json/wp/v2/posts", params=params)
        r.raise_for_status()
    return [_clean_post(p) for p in r.json()]


async def draft_post(
    domain: str,
    title: str,
    body: str,
    categories: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Create a draft post. Returns the saved post object."""
    site = _get_site(domain)
    payload: dict[str, Any] = {
        "title": title,
        "content": body,
        "status": "draft",
    }
    if categories:
        payload["categories"] = categories
    if tags:
        payload["tags"] = tags

    async with _client(site) as http:
        r = await http.post(
            f"{site['base_url']}/wp-json/wp/v2/posts", json=payload
        )
        r.raise_for_status()
    return _clean_post(r.json())


async def update_post(domain: str, post_id: int, **fields) -> dict:
    """Patch arbitrary fields on an existing post."""
    site = _get_site(domain)
    async with _client(site) as http:
        r = await http.patch(
            f"{site['base_url']}/wp-json/wp/v2/posts/{post_id}", json=fields
        )
        r.raise_for_status()
    return _clean_post(r.json())


async def publish_post(domain: str, post_id: int) -> dict:
    """Set a post's status to 'publish'."""
    return await update_post(domain, post_id, status="publish")


async def delete_post(domain: str, post_id: int) -> bool:
    """Move a post to trash. Returns True on success."""
    site = _get_site(domain)
    async with _client(site) as http:
        r = await http.delete(
            f"{site['base_url']}/wp-json/wp/v2/posts/{post_id}"
        )
        r.raise_for_status()
    return True


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def _clean_comment(raw: dict) -> dict:
    return {
        "id": raw.get("id"),
        "post": raw.get("post"),
        "author_name": raw.get("author_name"),
        "author_email": raw.get("author_email"),
        "date": raw.get("date"),
        "status": raw.get("status"),
        "content": raw.get("content", {}).get("rendered", ""),
        "link": raw.get("link"),
    }


async def list_comments(
    domain: str, status: str = "hold", limit: int = 20
) -> list[dict]:
    """Return pending (or other-status) comments."""
    site = _get_site(domain)
    params: dict[str, Any] = {"per_page": min(limit, 100), "status": status}
    async with _client(site) as http:
        r = await http.get(
            f"{site['base_url']}/wp-json/wp/v2/comments", params=params
        )
        r.raise_for_status()
    return [_clean_comment(c) for c in r.json()]


async def moderate_comment(
    domain: str, comment_id: int, action: str
) -> bool:
    """
    Moderate a comment. *action* must be one of:
    approve | hold | spam | trash
    """
    _VALID = {"approve", "hold", "spam", "trash"}
    if action not in _VALID:
        raise ValueError(f"action must be one of {_VALID}")

    status_map = {
        "approve": "approved",
        "hold": "hold",
        "spam": "spam",
        "trash": "trash",
    }
    site = _get_site(domain)
    async with _client(site) as http:
        r = await http.patch(
            f"{site['base_url']}/wp-json/wp/v2/comments/{comment_id}",
            json={"status": status_map[action]},
        )
        r.raise_for_status()
    return True


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------


async def upload_media(
    domain: str, file_path: str, alt_text: str = ""
) -> dict:
    """Upload a local file to the WordPress media library."""
    site = _get_site(domain)
    path = pathlib.Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Media file not found: {file_path}")

    mime_type, _ = mimetypes.guess_type(str(path))
    mime_type = mime_type or "application/octet-stream"

    headers = {
        "Authorization": _auth_header(site),
        "Content-Disposition": f'attachment; filename="{path.name}"',
        "Content-Type": mime_type,
    }
    if alt_text:
        headers["X-Wp-Alt-Text"] = alt_text

    async with httpx.AsyncClient(timeout=_TIMEOUT) as http:
        r = await http.post(
            f"{site['base_url']}/wp-json/wp/v2/media",
            headers=headers,
            content=path.read_bytes(),
        )
        r.raise_for_status()

    raw = r.json()
    return {
        "id": raw.get("id"),
        "title": raw.get("title", {}).get("rendered", ""),
        "alt_text": raw.get("alt_text", ""),
        "source_url": raw.get("source_url"),
        "link": raw.get("link"),
        "mime_type": raw.get("mime_type"),
    }


# ---------------------------------------------------------------------------
# WooCommerce
# ---------------------------------------------------------------------------


def _require_woo(site: dict, domain: str) -> None:
    if not site.get("has_woocommerce"):
        raise NotImplementedError(
            f"WooCommerce is not enabled for site '{domain}'"
        )


def _clean_product(raw: dict) -> dict:
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "status": raw.get("status"),
        "regular_price": raw.get("regular_price"),
        "sale_price": raw.get("sale_price"),
        "stock_status": raw.get("stock_status"),
        "permalink": raw.get("permalink"),
        "sku": raw.get("sku"),
    }


async def list_products(domain: str, limit: int = 20) -> list[dict]:
    """Return WooCommerce products (requires has_woocommerce=True)."""
    site = _get_site(domain)
    _require_woo(site, domain)
    params: dict[str, Any] = {"per_page": min(limit, 100)}
    async with _client(site) as http:
        r = await http.get(
            f"{site['base_url']}/wp-json/wc/v3/products", params=params
        )
        r.raise_for_status()
    return [_clean_product(p) for p in r.json()]


async def update_product_price(
    domain: str,
    product_id: int,
    regular_price: str,
    sale_price: str | None = None,
) -> dict:
    """Update regular (and optionally sale) price of a WooCommerce product."""
    site = _get_site(domain)
    _require_woo(site, domain)
    payload: dict[str, Any] = {"regular_price": regular_price}
    if sale_price is not None:
        payload["sale_price"] = sale_price

    async with _client(site) as http:
        r = await http.put(
            f"{site['base_url']}/wp-json/wc/v3/products/{product_id}",
            json=payload,
        )
        r.raise_for_status()
    return _clean_product(r.json())
