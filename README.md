# RUNNAUP — Paid Surveys + Paid Studies Board

Spelled **R-U-N-N-A-U-P**. Ken's board for paid surveys and paid research
studies, modeled on ClaimBoard / Workspace (FastAPI + SQLite, no-password
admin by Ken's standing order for these boards).

## Modes
- **📋 Surveys** — consumer panels (Branded Surveys, Survey Junkie, Swagbucks,
  Pinecone Research, Rakuten Insight, Ipsos iSay). Honest truth: pocket money,
  low $/hr.
- **🎓 Study Mode** — paid research studies / focus groups / interviews
  (Prolific, CloudResearch Connect, User Interviews, Respondent, dscout,
  PlaytestCloud). **Prolific, Connect, and User Interviews are study-type and
  usually the highest $/hr** — start there.

## Hard rules (enforced in the API, not just the UI)
1. **FREE ONLY.** Anything pay-to-join, paid plan, deposit, or
   purchase-required is rejected: `POST /api/admin/items` returns 400 unless
   `free_confirmed=true` and `requires_payment=false`. Every seeded item has
   `free_confirmed=1`.
2. **HONEST RULE — no fake answers, ever.** The bot finds panels, joins free
   accounts (Google sign-in OK where allowed), and preps surveys/studies with
   Ken's **real** demographic info, then queues them `ready`. **Ken himself
   must answer the opinion / experience questions.** A bot fake-answering
   surveys is fraud — it gets accounts banned and pay voided. There is no
   fake-answer engine in this app and one must never be built.
3. **Earnings are real or they are zero.** The earnings total counts ONLY
   rows with `status='paid'` AND `paid_amount > 0`. Typical/advertised pay
   on a card is potential, never earnings.

## Privacy
No DOB, phone number, or SSN is stored in this app or shown in any UI.
`/api/profile-prep` exposes only name + city/state/ZIP and a checklist of
screener questions Ken still needs to answer himself (household size,
employment, income range, race/ethnicity — only with his answer, marital
status, education, devices, car ownership). **Never invent those answers.**
Ken's full filing profile lives only in the goal workspace's `hidden_files`.

## Statuses
`found → joined → ready → started → completed → paid`, or `passed` at any point.

## Run locally
```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
# DB defaults to ./runnaup.db, override with RUNNAUP_DB=/path/runnaup.db
```

## Deploy
`render.yaml` is ready (service name `runnaup`, disk at `/data`) but
**NOT deployed** — deployment waits for Ken's go-ahead. No accounts have
been created and Ken has not been signed up for anything by this build.
