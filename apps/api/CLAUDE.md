# FastAPI Backend

## Quick Start

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

## Running Tests

```bash
pytest
pytest -v tests/test_health.py
```

## Linting

```bash
ruff check .
ruff format .
mypy app
```

## Adding a New Router

1. Create `app/routers/<resource>.py` with an `APIRouter`.
2. Add business logic in `app/services/<resource>.py`.
3. Register the router in `app/main.py`.
4. Add tests in `tests/test_<resource>.py`.

## Web Push (VAPID keys)

The push notification service uses Voluntary Application Server Identification
(VAPID) for authenticated Web Push delivery. Generate a key pair once per
deployment.

```bash
cd apps/api
source .venv/bin/activate

python - <<'PY'
import base64
from py_vapid import Vapid
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

v = Vapid()
v.generate_keys()

# Public key: 65-byte uncompressed point, base64url-encoded (no padding)
public_raw = v.public_key.public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint,
)
public_b64 = base64.urlsafe_b64encode(public_raw).decode().rstrip("=")

# Private key: 32-byte scalar, base64url-encoded (no padding)
priv_int = v.private_key.private_numbers().private_value
priv_raw = priv_int.to_bytes(32, "big")
private_b64 = base64.urlsafe_b64encode(priv_raw).decode().rstrip("=")

print(f"VAPID_PUBLIC_KEY={public_b64}")
print(f"VAPID_PRIVATE_KEY={private_b64}")
print(f"NEXT_PUBLIC_VAPID_PUBLIC_KEY={public_b64}")
PY
```

Copy the values into both `apps/api/.env` (private + public) and
`apps/web/.env.local` (public only). Set `PUSH_ENABLED=true` to activate
delivery. The `VAPID_SUBJECT` value should be a valid `mailto:` URL.

The push service is exposed under `/api/push/*` (subscribe, unsubscribe,
vapid-public-key, test). The frontend hook `usePushSubscription` automatically
fetches the public key from the API if the env var is unset.
