# O3DE Pilot - Registry Authentication
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Token-based authentication for private O3DE registries.

Tokens are stored per-registry URL in a local credentials file.
The file lives at ~/.o3de/credentials.json and is NOT committed to repos.
"""

import json
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_CREDENTIALS_FILE = "credentials.json"


def get_credentials_path() -> Path:
    """Return the path to the credentials file."""
    from o3de_pilot.core.paths import get_o3de_home
    return get_o3de_home() / _CREDENTIALS_FILE


def get_token(registry_url: str) -> Optional[str]:
    """Get the auth token for a registry URL.

    Matches by origin (scheme + host + port). Returns None if no token is stored.
    """
    creds = _load_credentials()
    key = _registry_key(registry_url)
    entry = creds.get(key)
    if entry and isinstance(entry, dict):
        return entry.get("token")
    return None


def set_token(registry_url: str, token: str) -> None:
    """Store an auth token for a registry URL."""
    creds = _load_credentials()
    key = _registry_key(registry_url)
    creds[key] = {"token": token}
    _save_credentials(creds)
    logger.info(f"Token saved for {key}")


def remove_token(registry_url: str) -> bool:
    """Remove the auth token for a registry URL.

    Returns True if a token was removed, False if none existed.
    """
    creds = _load_credentials()
    key = _registry_key(registry_url)
    if key in creds:
        del creds[key]
        _save_credentials(creds)
        return True
    return False


def list_registries() -> list[str]:
    """List all registry URLs that have stored tokens."""
    creds = _load_credentials()
    return list(creds.keys())


def get_auth_headers(registry_url: str) -> dict[str, str]:
    """Get HTTP headers for authenticated requests to a registry.

    Returns an empty dict if no token is stored.
    """
    token = get_token(registry_url)
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _registry_key(url: str) -> str:
    """Normalize a registry URL to a key for credential storage."""
    parsed = urlparse(url)
    # Use scheme + netloc as the key
    if parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return url.rstrip("/")


def _load_credentials() -> dict:
    """Load credentials from disk."""
    path = get_credentials_path()
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load credentials: {e}")
    return {}


def _save_credentials(creds: dict) -> None:
    """Save credentials to disk with restrictive permissions."""
    path = get_credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(creds, f, indent=2)
    # Restrict file permissions (owner-only on Unix)
    try:
        import os
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows doesn't support chmod the same way
