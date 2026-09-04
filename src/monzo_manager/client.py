import httpx

from monzo_manager.config import settings
from monzo_manager.db import SessionLocal, MonzoState
from monzo_manager.log import setup_rotating_logger

MONZO_API_BASE = "https://api.monzo.com"
logger = setup_rotating_logger()

# Global cache to avoid querying DB for access token on every single request
CURRENT_ACCESS_TOKEN = ""


def get_valid_refresh_token() -> str:
    """Retrieves the latest refresh token from SQLite. Seeds it from config if missing."""
    with SessionLocal() as db:
        state = db.query(MonzoState).filter(MonzoState.id == 1).first()
        if not state:
            logger.info("🌱 [DB] Database is empty. Seeding with monzo_initial_refresh_token from config...")
            state = MonzoState(id=1, refresh_token=settings.monzo_initial_refresh_token)
            db.add(state)
            db.commit()
        return state.refresh_token


async def refresh_monzo_tokens() -> bool:
    """Exchanges refresh token for a new pair via Monzo API and updates SQLite."""
    global CURRENT_ACCESS_TOKEN

    current_refresh = get_valid_refresh_token()
    url = f"{MONZO_API_BASE}/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": settings.monzo_client_id,
        "client_secret": settings.monzo_client_secret,
        "refresh_token": current_refresh,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, data=data)
            if response.status_code == 200:
                tokens = response.json()
                CURRENT_ACCESS_TOKEN = tokens["access_token"]

                with SessionLocal() as db:
                    state = db.query(MonzoState).filter(MonzoState.id == 1).first()
                    state.access_token = tokens["access_token"]
                    state.refresh_token = tokens["refresh_token"]
                    db.commit()

                logger.info("🔄 [AUTH] Tokens rotated and stored in SQLite database.")
                return True
            logger.error(f"❌ [AUTH] Token rotation failed: {response.text}")
            return False
        except Exception:
            logger.exception("❌ [AUTH] Critical error during token refresh")
            return False


async def monzo_api_request(method: str, endpoint: str, **kwargs) -> httpx.Response:
    """Wrapper around HTTP requests to Monzo. Handles automatic 401 token refresh."""
    global CURRENT_ACCESS_TOKEN
    url = f"{MONZO_API_BASE}{endpoint}"

    if not CURRENT_ACCESS_TOKEN:
        await refresh_monzo_tokens()

    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {CURRENT_ACCESS_TOKEN}"

    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, headers=headers, **kwargs)

        if response.status_code == 401:
            logger.warning("🔄 [AUTH] Access token expired (401). Triggering automatic refresh...")
            if await refresh_monzo_tokens():
                headers["Authorization"] = f"Bearer {CURRENT_ACCESS_TOKEN}"
                response = await client.request(method, url, headers=headers, **kwargs)

        return response


async def fetch_current_balance() -> int:
    """Fetches current account balance in cents."""
    params = {"account_id": settings.monzo_account_id}
    response = await monzo_api_request("GET", "/balance", params=params)
    if response.status_code == 200:
        return response.json().get("balance", 0)
    else:
        raise RuntimeError(f"Cannot get balance: {response.json()}")


async def fetch_pot_balance(pot_id: str) -> int:
    """Fetches pot balance in cents."""
    params = {"current_account_id": settings.monzo_account_id}
    response = await monzo_api_request("GET", "/pots", params=params)
    if response.status_code != 200:
        raise RuntimeError(f"Cannot get pot '{pot_id}' balance: {response.json()}")
    for pot in response.json().get("pots", []):
        if pot_id == pot.get("id"):
            return pot.get("balance", 0)
    raise ValueError(f"Cannot find pot '{pot_id}'")


async def withdraw_from_pot(amount_cents: int, dedupe_id: str) -> tuple[bool, int]:
    """Withdraws money from the ongoing buffer pot to the main account."""
    data = {
        "destination_account_id": settings.monzo_account_id,
        "amount": str(amount_cents),
        "dedupe_id": dedupe_id
    }
    try:
        response = await monzo_api_request("PUT", f"/pots/{settings.monzo_ongoing_pot_id}/withdraw", data=data)
        if response.status_code == 200:
            logger.info(f"POT -> €{amount_cents / 100} -> MAIN")
            return True, response.json().get("balance", 0)
        else:
            logger.error(f"❌ Monzo API {response.status_code}: {response.text}")
            return False, 0
    except Exception:
        logger.exception("❌ Monzo API is unavailable")
        return False, 0


async def deposit_to_pot(pot_id: str, amount_cents: int, dedupe_id: str) -> bool:
    """Deposits money from the main account into the savings pot."""
    data = {
        "source_account_id": settings.monzo_account_id,
        "amount": str(amount_cents),
        "dedupe_id": dedupe_id
    }
    response = await monzo_api_request("POST", f"/pots/{pot_id}/deposit", data=data)
    return response.status_code == 200


async def annotate_transaction(transaction_id: str, notes: str) -> bool:
    """Custom transaction notes."""
    data = {
        "metadata[notes]": notes
    }
    try:
        response = await monzo_api_request("PATCH", f"/transactions/{transaction_id}", data=data)

        if response.status_code == 200:
            logger.info(f"📝 Successfully annotated transaction {transaction_id}")
            return True
        else:
            logger.error(f"❌ Failed to annotate transaction: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Error during transaction annotation: {e}")
        return False
