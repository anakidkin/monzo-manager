### 📋 Monzo Manager: TODO List & Roadmap

* [ ] TG whitelist for family members
* [ ] TG commands:
  * [ ] "/add {amount}" to ongoing
  * [ ] salary retry

#### 🔵 Phase 3: Smart Features (BACKLOG)

* [ ] **Task 2: Subscription Calendar (Predictive Top-up)**
* *Context:* Big payments (like a €120 annual insurance bill) will fail *before* the webhook triggers because the main
  account only holds €100.
* [ ] Design a simple storage (JSON or DB table) for expected large bills (date + amount).
* [ ] **Question 2:** How do we trigger the pre-emptive top-up?
* *Option A:* Since we don't want a background cron/scheduler, can we check the calendar and boost the buffer *at
  application startup* or *on every incoming webhook request*?
