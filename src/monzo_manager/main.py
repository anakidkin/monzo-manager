import uuid
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, status

from monzo_manager.config import settings
from monzo_manager.log import setup_rotating_logger

MONZO_API_BASE = "https://api.monzo.com"

load_dotenv()

logger = setup_rotating_logger()


async def withdraw_from_pot(amount_cents: int, dedupe_id: str) -> bool:
    url = f"{MONZO_API_BASE}/pots/{settings.monzo_savings_pot_id}/withdraw"
    headers = {"Authorization": f"Bearer {settings.monzo_access_token}"}

    data = {
        "destination_account_id": settings.monzo_account_id,
        "amount": str(amount_cents),
        "dedupe_id": dedupe_id
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.put(url, headers=headers, data=data)
            if response.status_code == 200:
                logger.info(f"POT -> €{amount_cents / 100} -> MAIN")
                return True
            else:
                logger.error(f"❌ Monzo API {response.status_code}: {response.text}")
                return False
        except Exception:
            logger.exception("❌ Monzo API is unavailable")
            return False


async def check_and_replenish_balance(current_balance_cents: int, trigger_source: str, tx_id: str = None) -> dict:
    logger.info(f"🔄 [{trigger_source}] Current balance: €{current_balance_cents / 100}")

    if current_balance_cents < settings.target_buffer_cents:
        needed_amount = settings.target_buffer_cents - current_balance_cents
        logger.info(
            f"⚠️ [{trigger_source}] Balance below limit (€{settings.target_buffer_cents / 100}). Add: €{needed_amount / 100}")

        # Если это вебхук, используем ID транзакции, если старт приложения — генерируем уникальный uuid
        dedupe_id = f"buf_webhook_{tx_id}" if tx_id else f"buf_startup_{uuid.uuid4().hex}"

        success = await withdraw_from_pot(amount_cents=needed_amount, dedupe_id=dedupe_id)
        if success:
            return {"status": "buffer_replenished", "amount_added": needed_amount}
        else:
            return {"status": "failed_to_replenish"}

    logger.info(f"✅ [{trigger_source}] Balance is OK.")
    return {"status": "ok", "reason": "balance is sufficient"}


async def fetch_current_balance() -> int:
    url = f"{MONZO_API_BASE}/balance"
    headers = {"Authorization": f"Bearer {settings.monzo_access_token}"}
    params = {"account_id": settings.monzo_account_id}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json().get("balance", 0)
        else:
            raise Exception(f"Cannot get balance: {response.status_code}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Initial balance check...")
    try:
        startup_balance = await fetch_current_balance()
        await check_and_replenish_balance(current_balance_cents=startup_balance, trigger_source="STARTUP")
    except Exception:
        logger.exception("❌ Cannot verify balance")

    yield
    logger.info("🛑 App is stopping...")


app = FastAPI(title="Monzo Buffer Bot", lifespan=lifespan)


@app.post("/webhook", status_code=status.HTTP_200_OK)
async def handle_monzo_webhook(request: Request):
    payload = await request.json()

    if payload.get("type") != "transaction.created":
        return {"status": "ignored", "reason": "not a transaction"}

    tx_data = payload.get("data", {})
    current_balance = tx_data.get("account_balance")
    tx_id = tx_data.get("id")

    if current_balance is None:
        return {"status": "error", "reason": "no balance data in webhook"}

    result = await check_and_replenish_balance(
        current_balance_cents=current_balance,
        trigger_source="WEBHOOK",
        tx_id=tx_id
    )
    return result
