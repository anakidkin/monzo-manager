# Monzo Buffer Manager

An event-driven financial assistant built with FastAPI and Docker. It monitors your main Monzo account balance via
webhooks and ensures a constant €100 buffer by dynamically top-up from an ongoing spending pot. It also automatically
sweeps leftovers from the previous month into a savings pot upon salary arrival.

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

---

## ⚙️ Setup & First-Time Authentication

### 1. Environment Configuration

Create a `.env` file in the project root based on the template below:

```bash
# App Settings
TARGET_BUFFER_CENTS=10000        # €100.00 target buffer balance
MIN_SALARY_AMOUNT_CENTS=150000   # €1,500.00 minimum salary threshold

# Monzo Client Credentials
MONZO_ACCOUNT_ID=acc_your_account_id
MONZO_CLIENT_ID=oauth2client_your_client_id
MONZO_CLIENT_SECRET=src_your_client_secret
MONZO_ONGOING_POT_ID=pot_your_buffer_pot_id
MONZO_NZ_POT_ID=pot_your_savings_pot_id

# Monzo Initial OAuth Token (Seeded into SQLite on first launch)
MONZO_INITIAL_REFRESH_TOKEN=ref_your_initial_refresh_token

# Telegram Integration
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyZ
TELEGRAM_CHAT_ID=123456789

```

---

### 2. Initial Monzo OAuth Bootstrap

Since Monzo requires interactive user approval to issue the first token, follow these steps to obtain your initial
`refresh_token`:

#### Step A: Open the Authorization URL

Construct the authorization URL with your `client_id` and registered `redirect_uri`, then open it in your browser:

```text
https://auth.monzo.com/?client_id=YOUR_CLIENT_ID&redirect_uri=YOUR_REDIRECT_URI&response_type=code&state=random_string_123

```

1. Log in with your email and authorize the application.
2. Open your Monzo mobile app and **approve the login request**.
3. After approval, the browser will redirect you to your `redirect_uri` with a `code` parameter in the URL:
   `YOUR_REDIRECT_URI?code=arg_0000...&state=random_string_123`

#### Step B: Exchange Code for Initial Tokens

Exchange the authorization code for your first pair of tokens using cURL:

```bash
curl -X POST https://api.monzo.com/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=authorization_code" \
  --data-urlencode "client_id=YOUR_CLIENT_ID" \
  --data-urlencode "client_secret=YOUR_CLIENT_SECRET" \
  --data-urlencode "redirect_uri=YOUR_REDIRECT_URI" \
  --data-urlencode "code=YOUR_AUTHORIZATION_CODE"

```

Copy the returned `refresh_token` into your `.env` file as `MONZO_INITIAL_REFRESH_TOKEN`. Once the application starts,
it will automatically store and rotate this token in SQLite.

---

## 🚨 EXPLOITATION NOTES

Every 90 days, you need to renew the client's permission in the Monzo bank application under:

**Settings -> Privacy & Security -> Manage Apps -> Refresh Permissions**
