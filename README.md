# Monzo Buffer Manager

An event-driven financial assistant built with FastAPI and Docker. It monitors your main Monzo account balance via webhooks and ensures a constant €100 buffer by dynamically top-up from an ongoing spending pot. It also automatically sweeps leftovers from the previous month into a savings pot upon salary arrival.

## 🛠️ Tech Stack

- **Backend:** Python 3.14 + FastAPI + Uvicorn
- **Database & Migrations:** SQLite + SQLAlchemy + Alembic
- **Dependency Management:** Poetry (with `src` layout)
- **Deployment:** Docker + GitHub Actions (CI/CD) + Oracle Cloud (Ubuntu VM)

---

## 📂 Project Structure

```text
├── .github/workflows/
│   └── deploy.yml          # GitHub Actions deployment pipeline
├── alembic/                # Database migrations directory
├── src/
│   └── monzo_manager/      # Main application package
│       ├── db.py           # SQLite & SQLAlchemy setup
│       ├── client.py       # Monzo API client
│       ├── config.py       # Pydantic-settings configuration
│       ├── main.py         # FastAPI app & Monzo logic
│       └── telegram.py     # Telegram client
├── alembic.ini             # Alembic configuration
├── Dockerfile              # Multi-stage production build
├── pyproject.toml          # Poetry configuration & metadata
└── README.md
```

## 🚨 EXPLOITATION NOTES  

Every 90 days, you need to renew the client's permission in the Monzo bank application under:  
**Settings -> Privacy & Security -> Manage Apps -> Refresh Permissions**