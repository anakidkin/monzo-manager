import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from starlette.status import HTTP_200_OK

from monzo_manager.client import fetch_current_balance, withdraw_from_pot, deposit_to_nz_pot, annotate_transaction
from monzo_manager.config import settings
from monzo_manager.db import SessionLocal, BotActionLog
from monzo_manager.log import setup_rotating_logger
from monzo_manager.telegram import send_telegram_notification

load_dotenv()
logger = setup_rotating_logger()

BOT_DEDUP_REPLENISH_PREFIX = "buf_"
BOT_DEDUP_SWEEP_PREFIX = "sweep_"


async def check_and_replenish_balance(current_balance_cents: int, trigger_source: str, tx_id: str = None) -> dict:
    logger.info(f"🔄 [{trigger_source}] Current balance: €{current_balance_cents / 100}")

    if current_balance_cents < settings.target_buffer_cents:
        needed_amount = settings.target_buffer_cents - current_balance_cents
        logger.info(
            f"⚠️ [{trigger_source}] Balance below limit (€{settings.target_buffer_cents / 100}). Add: €{needed_amount / 100}")

        dedupe_id = f"{BOT_DEDUP_REPLENISH_PREFIX}webhook_{tx_id}" if tx_id else f"{BOT_DEDUP_REPLENISH_PREFIX}startup_{uuid.uuid4().hex}"

        success = await withdraw_from_pot(amount_cents=needed_amount, dedupe_id=dedupe_id)
        if success:
            log_action_to_db(
                action_type="REPLENISH",
                status="SUCCESS",
                amount_cents=needed_amount,
                trigger_source=trigger_source,
                tx_id=tx_id
            )
            formatted_amount = f"€{needed_amount / 100:.2f}"
            new_balance = f"€{settings.target_buffer_cents / 100:.2f}"
            await send_telegram_notification(
                f"📥 <b>Buffer Replenished [{trigger_source}]</b>\n"
                f"Pulled <b>{formatted_amount}</b> from Ongoing Pot to restore target buffer.\n"
                f"Current balance is now: <b>{new_balance}</b>"
            )
            return {"status": "buffer_replenished", "amount_added": needed_amount}
        else:
            log_action_to_db(
                action_type="REPLENISH",
                status="FAILED",
                amount_cents=needed_amount,
                trigger_source=trigger_source,
                tx_id=tx_id,
                error_message="Monzo API withdrawal failed (check container logs for details)"
            )
            return {"status": "failed_to_replenish"}

    logger.info(f"✅ [{trigger_source}] Balance is OK.")
    return {"status": "ok", "reason": "balance is sufficient"}


async def sweep_old_balance(current_balance_cents: int, salary_amount_cents: int, tx_id: str):
    balance_before_salary = current_balance_cents - salary_amount_cents

    if balance_before_salary > settings.target_buffer_cents:
        sweep_amount = balance_before_salary - settings.target_buffer_cents
        logger.info(f"🧹 Add €{sweep_amount / 100} to NZ...")
        success = await deposit_to_nz_pot(amount_cents=sweep_amount, dedupe_id=f"{BOT_DEDUP_SWEEP_PREFIX}{tx_id}")
        if success:
            log_action_to_db(
                action_type="SWEEP",
                status="SUCCESS",
                amount_cents=sweep_amount,
                trigger_source="WEBHOOK",
                tx_id=tx_id
            )
            formatted_sweep = f"€{sweep_amount / 100:.2f}"
            formatted_salary = f"€{salary_amount_cents / 100:.2f}"
            await send_telegram_notification(
                f"🧹 <b>Salary Sweep Executed</b>\n"
                f"Received salary: <b>{formatted_salary}</b>\n"
                f"Swept <b>{formatted_sweep}</b> (old balance excess) into <b>NZ Savings Pot</b>."
            )
        else:
            log_action_to_db(
                action_type="SWEEP",
                status="FAILED",
                amount_cents=sweep_amount,
                trigger_source="WEBHOOK",
                tx_id=tx_id,
                error_message="Monzo API deposit failed (check container logs for details)"
            )
            logger.warning("❌ [SWEEP] Cannot save money to NZ.")


def log_action_to_db(action_type: str,
                     status: str,
                     amount_cents: int,
                     trigger_source: str,
                     tx_id: str = None,
                     error_message: str = None):
    """Saves a bot action attempt (success or failure) to the SQLite database."""
    with SessionLocal() as db:
        log_entry = BotActionLog(
            action_type=action_type,
            status=status,
            amount_cents=amount_cents,
            trigger_source=trigger_source,
            tx_id=tx_id,
            error_message=error_message
        )
        db.add(log_entry)
        db.commit()


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


@app.post("/webhook", status_code=HTTP_200_OK)
async def handle_monzo_webhook(request: Request):
    payload = await request.json()
    logger.info(f"webhook received: {payload}")

    if payload.get("type") != "transaction.created":
        return {"status": "ignored", "reason": "not a transaction.created event"}

    tx_data = payload.get("data", {})
    tx_id = tx_data.get("id")
    tx_amount = tx_data.get("amount", 0)  # positive for income
    category = tx_data.get("category")
    scheme = tx_data.get("scheme")
    metadata = tx_data.get("metadata", {})
    dedupe_id = metadata.get("dedupe_id", "")
    notes = metadata.get("notes", "")

    if not notes:
        if dedupe_id.startswith(BOT_DEDUP_REPLENISH_PREFIX):
            await annotate_transaction(tx_id, "🤖 Monzo Manager Bot: Ongoing replenished")
        elif dedupe_id.startswith(BOT_DEDUP_SWEEP_PREFIX):
            await annotate_transaction(tx_id, "🤖 Monzo Manager Bot: Sweep to NZ")

    if scheme == "pot_generic":
        pot_id = tx_data.get("metadata", {}).get("pot_id", "")
        if pot_id == settings.monzo_ongoing_pot_id:
            logger.info(f"🔄 Ignored internal pot transfer (tx_id: {tx_id})")
            return {"status": "ignored", "reason": "internal pot transfer"}

    try:
        current_balance = await fetch_current_balance()
    except Exception:
        logger.exception("❌ Failed to fetch balance from Monzo API")
        return {"status": "error", "reason": "failed to fetch current balance"}

    if tx_amount >= settings.min_salary_amount_cents or category == "income":
        logger.info(f"🎉 SALARY: €{tx_amount / 100}!")
        await sweep_old_balance(current_balance, tx_amount, tx_id)
        return {"status": "salary_processed_and_swept"}

    result = await check_and_replenish_balance(
        current_balance_cents=current_balance,
        trigger_source="WEBHOOK",
        tx_id=tx_id
    )
    return result
