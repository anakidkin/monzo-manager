import uuid
from asyncio import sleep
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from starlette.status import HTTP_200_OK

from monzo_manager.client import fetch_current_balance, withdraw_from_pot, deposit_to_pot, annotate_transaction, \
    fetch_pot_balance
from monzo_manager.config import settings
from monzo_manager.db import SessionLocal, BotActionLog
from monzo_manager.log import setup_rotating_logger
from monzo_manager.telegram import send_telegram_notification

load_dotenv()
logger = setup_rotating_logger()

BOT_DEDUP_REPLENISH_PREFIX = "buf_"
BOT_DEDUP_SWEEP_PREFIX = "sweep_"
BOT_DEDUP_NZ_PREFIX = "nz_"


async def check_and_replenish_balance(trigger_source: str, tx_id: str = None) -> dict:
    try:
        current_balance_cents = await fetch_current_balance()
    except Exception:
        logger.exception("❌ Failed to fetch balance from Monzo API")
        return {"status": "error", "reason": "failed to fetch current balance"}
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


async def ongoing_to_nz(tx_id: str) -> None:
    """
        Move unused amount from ONGOING to NZ.
        1. get ONGOING amount and move the same value from current balance to NZ
          1.1. if not enough (monthly saving > salary ^_^) - congrats TG msg and do nothing
    """
    savings = await fetch_pot_balance(settings.monzo_ongoing_pot_id)
    current_balance_cents = await fetch_current_balance()
    if current_balance_cents > savings:
        logger.info(f"💰 Add €{savings / 100} to NZ...")
        success = await deposit_to_pot(settings.monzo_nz_pot_id, savings, f"{BOT_DEDUP_NZ_PREFIX}{tx_id}")
        if success:
            log_action_to_db(
                action_type="SWEEP",
                status="SUCCESS",
                amount_cents=savings,
                trigger_source="WEBHOOK",
                tx_id=tx_id
            )
            await send_telegram_notification(f"💰 Congrats! You saved <b>€{savings / 100:.2f}</b> this month.")
        else:
            log_action_to_db(
                action_type="SWEEP",
                status="FAILED",
                amount_cents=savings,
                trigger_source="WEBHOOK",
                tx_id=tx_id,
                error_message="Monzo API deposit failed (check container logs for details)"
            )
            logger.warning("❌ [SWEEP] Cannot save money to NZ.")
    else:
        logger.info(f"Saving > current balance: {savings / 100}>={current_balance_cents / 100}")
        await send_telegram_notification(
            f"🥳 <b>Wow, it seems your saving is BIGGER than income!</b>\n"
            f"{savings / 100} > {current_balance_cents / 100}\n"
            f"Please, process it manually."
        )


async def restore_ongoing(tx_id: str) -> None:
    current_balance_cents = await fetch_current_balance()
    ongoing = current_balance_cents - settings.target_buffer_cents
    success = await deposit_to_pot(settings.monzo_ongoing_pot_id, ongoing, f"{BOT_DEDUP_SWEEP_PREFIX}{tx_id}")
    if success:
        log_action_to_db(
            action_type="SALARY",
            status="SUCCESS",
            amount_cents=ongoing,
            trigger_source="WEBHOOK",
            tx_id=tx_id
        )
        formatted_sweep = f"€{ongoing / 100:.2f}"
        await send_telegram_notification(f"🧹 <b>Monthly budget updated</b>: {formatted_sweep}")
    else:
        log_action_to_db(
            action_type="SALARY",
            status="FAILED",
            amount_cents=ongoing,
            trigger_source="WEBHOOK",
            tx_id=tx_id,
            error_message="Monzo API deposit failed (check container logs for details)"
        )
        logger.warning("❌ [SWEEP] Cannot update ongoing.")
        await send_telegram_notification("❌ <b>Monthly budget update FAILED</b>")


async def process_salary(tx_id: str) -> None:
    """
    Move unused amount from ONGOING to NZ, restore the main balance.
    1. get ONGOING amount and move the same value from current balance to NZ
      1.1. if not enough (monthly saving > salary ^_^) - congrats TG msg and do nothing
    2. calculate sweep_amount and move to ONGOING
    """
    try:
        await ongoing_to_nz(tx_id)
    except Exception as e:
        msg = "❌ Failed to move savings to NZ"
        logger.exception(msg)
        await send_telegram_notification(f"{msg}: {e}")

    try:
        await restore_ongoing(tx_id)
    except Exception as e:
        msg = "❌ Failed to restore ONGOING"
        logger.exception(msg)
        await send_telegram_notification(f"{msg}: {e}")


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
        await check_and_replenish_balance(trigger_source="STARTUP")
    except Exception:
        logger.exception("❌ Cannot verify balance")

    yield
    logger.info("🛑 App is stopping...")


app = FastAPI(title="Monzo Buffer Bot", lifespan=lifespan)


def is_salary(payload: dict) -> bool:
    """
    It's a salary if it's an income with a predefined value.
    XXX: find better definition
    """
    tx_data = payload.get("data", {})
    tx_amount = tx_data.get("amount", 0)  # positive for income
    category = tx_data.get("category")
    return tx_amount >= settings.min_salary_amount_cents or category == "income"


@app.post("/webhook", status_code=HTTP_200_OK)
async def handle_monzo_webhook(request: Request):
    payload = await request.json()
    payload_type = payload.get("type")
    logger.debug(f"webhook: {payload}")

    if payload_type != "transaction.created":
        if payload_type != "transaction.updated":
            logger.info(f"unknown payload type: {payload}")
        return {"status": "ignored", "reason": "not a transaction.created event"}

    tx_data = payload.get("data", {})
    tx_id = tx_data.get("id")
    tx_amount = tx_data.get("amount", 0)  # positive for income
    scheme = tx_data.get("scheme")
    dedupe_id = tx_data.get("dedupe_id", "")
    notes = tx_data.get("notes", "")

    if not notes:
        if f":{BOT_DEDUP_REPLENISH_PREFIX}" in dedupe_id:
            await annotate_transaction(tx_id, "🤖 Monzo Manager Bot: Ongoing replenished")
        elif f":{BOT_DEDUP_SWEEP_PREFIX}" in dedupe_id:
            await annotate_transaction(tx_id, "🤖 Monzo Manager Bot: Sweep to NZ")

    if scheme == "pot_generic":
        pot_id = tx_data.get("metadata", {}).get("pot_id", "")
        if pot_id == settings.monzo_ongoing_pot_id:
            logger.info(f"🔄 Ignored internal pot transfer (tx_id: {tx_id})")
            return {"status": "ignored", "reason": "internal pot transfer"}

    if is_salary(payload):
        logger.info(f"🎉 SALARY: €{tx_amount / 100}!")
        await sleep(10)  # await for salary sorter to apply
        await process_salary(tx_id)
        return {"status": "salary_processed_and_swept"}

    result = await check_and_replenish_balance(
        trigger_source="WEBHOOK",
        tx_id=tx_id
    )
    return result
