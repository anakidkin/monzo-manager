### 📋 Monzo Manager: TODO List & Roadmap

#### 🟢 Phase 1: Infrastructure & Core (DONE)

* [x] Setup lightweight multi-stage `Dockerfile` with Poetry.
* [x] Configure isolated Python virtual environment (`.venv`) inside container.
* [x] Setup GitHub Actions CI/CD for secure deployment to Oracle Cloud.
* [x] Fix port collision on the server (moved app to external port `8080`).
* [x] Clean up code and switch logs entirely to English.

---

#### 🟡 Phase 2: Token Management & Auth (CURRENT)

* [ ] **Implement Token Refresh Logic:**
* [ ] Add `client_id`, `client_secret`, and `refresh_token` to settings.
* [ ] Create interceptor/helper for Monzo API requests to handle `401 Unauthorized`.


* [ ] **Solve Refresh Token Persistence:**
* *Context:* Every time we use a `refresh_token`, Monzo gives us a *new* one, and the old one expires. If the container
  restarts, it shouldn't read the old expired token from `.env`.
* **Question 1:** Where do we save the new `refresh_token`?
* *Option A:* Rewrite `.env` file directly on the host machine using a Docker volume mount.
* *Option B:* Bring in a lightweight SQLite database file (also mounted via volume) to store tokens and system state.

---

#### 🔵 Phase 3: Smart Features (BACKLOG)

* [x] **Task 1: Salary Sweep (Event-Driven)**
* [x] Integrate logic into `/webhook` to detect incoming salary (`category == "income"` or large amount).
* [x] Calculate leftover balance from the *previous* month.
* [x] Automatically sweep the leftovers into `monzo_nz_pot_id` (Savings).
* [x] Let Salary Sorter run, then automatically top up the main account back to €100 from `monzo_ongoing_pot_id` if it
  drops.


* [ ] **Task 2: Subscription Calendar (Predictive Top-up)**
* *Context:* Big payments (like a €120 annual insurance bill) will fail *before* the webhook triggers because the main
  account only holds €100.
* [ ] Design a simple storage (JSON or DB table) for expected large bills (date + amount).
* [ ] **Question 2:** How do we trigger the pre-emptive top-up?
* *Option A:* Since we don't want a background cron/scheduler, can we check the calendar and boost the buffer *at
  application startup* or *on every incoming webhook request*?


* [ ] **Task 3: Telegram notifications on any action
* 