import datetime

from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:////app/data/monzo.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class MonzoState(Base):
    __tablename__ = "monzo_state"

    id = Column(Integer, primary_key=True, index=True, default=1)
    access_token = Column(String, nullable=True)
    refresh_token = Column(String, nullable=False)
    updated_at = Column(DateTime,
                        default=datetime.datetime.now(datetime.UTC),
                        onupdate=datetime.datetime.now(datetime.UTC)
                        )


class BotActionLog(Base):
    __tablename__ = "bot_action_logs"

    id = Column(Integer, primary_key=True, index=True)
    action_type = Column(String, nullable=False)  # 'REPLENISH' or 'SWEEP'
    status = Column(String, nullable=False)  # 'SUCCESS' or 'FAILED'
    amount_cents = Column(Integer, nullable=False)
    trigger_source = Column(String, nullable=False)  # 'STARTUP' or 'WEBHOOK'
    tx_id = Column(String, nullable=True)
    error_message = Column(String, nullable=True)  # Details if failed
    created_at = Column(DateTime, default=datetime.datetime.now(datetime.UTC))
