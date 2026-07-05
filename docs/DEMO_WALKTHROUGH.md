# Demo Walkthrough (for interviews)

Use this as a **5-minute script** when demoing CricketPulse to a recruiter or
interviewer. Every claim is directly backed by code in this repo.

---

## 0. The 30-second pitch

> "I built a real-time analytics platform that streams simulated live IPL
> match data through Kafka into a data warehouse, uses a machine-learning
> model to predict win probability after every ball, and lets you ask the
> data any question in plain English using a Google Gemini text-to-SQL agent.
> It's the same architecture Cricbuzz or a fintech company would use — just
> applied to a domain everyone in India understands."

Recruiter thought bubble: *"Data engineering + ML + GenAI + dashboards + Docker,
all working, all shown live. This person understands production systems."*

---

## 1. Show the architecture (30 sec)

Open `README.md` and scroll to the architecture diagram.

Say:
- "**Producer**: a match simulator generating one ball every 1.5 seconds."
- "**Kafka**: the streaming backbone — the same tech Uber, LinkedIn, and Netflix use."
- "**Consumer**: writes raw events into the bronze layer of a medallion warehouse."
- "**Airflow**: rebuilds silver + gold aggregates every minute."
- "**ML**: gradient-boosting classifier that predicts win probability from
   just 14 numeric features — 72.8% accuracy on held-out matches."
- "**GenAI**: LangChain + Gemini turns English into DuckDB SQL,
   runs it read-only, then rephrases the result."

---

## 2. Start the demo (60 sec)

```powershell
# One-command startup:
.\scripts\start_all.ps1
```

While that runs, open **3 tabs**:
1. **Streamlit** — http://localhost:8501
2. **Kafka UI** — http://localhost:8090
3. **Airflow** — http://localhost:8080 (admin/admin)

---

## 3. Walk through Kafka UI (30 sec)

Open the `balls.raw` topic → show live JSON messages arriving every 1.5 sec.

Point out:
- One ball = one Kafka message
- Match ID as the partition key -> guarantees order per match
- Second topic `balls.predictions` -> shows ML output being republished

---

## 4. Walk through the dashboard (2 min)

**Left column — Innings 1**
- Score updates in real time (auto-refresh every 3s).

**Win-probability chart**
- "Watch this line swing when a wicket falls."
- "See how it stabilizes at 50-50 in innings 1 and diverges violently in
  innings 2 as the chase becomes clearer."

**AI Expert Take**
- "Gemini is generating this paragraph fresh every 3 seconds based on the
  current state and the ML win probability."

**Batter / Bowler scorecards**
- "These come from the GOLD layer — refreshed by Airflow (or synchronously
  by the consumer every 6 balls)."

**Live Ball-by-Ball Feed**
- Point out the emoji tags: `[6]`, `[W]`, `[4]`, `[+wd]`.

---

## 5. Ask the AI Analyst (90 sec) — the wow moment

Type into the chat:
1. **"Who has the highest strike rate in this match?"**
   → answer + expandable SQL panel
2. **"What was the biggest over so far?"**
3. **"Show the win probability trend in the last 5 overs."**
4. **"Predict the final score if the current run rate continues."**

Say:
- "Every question becomes a real DuckDB SQL query. The LLM never touches
  the data directly — I gave it a schema hint and a strict rule: read-only
  SELECTs only. That's how you build GenAI apps that don't hallucinate."

---

## 6. Show Airflow (30 sec)

Open http://localhost:8080 → click the `cricketpulse_etl` DAG.

Point out:
- Runs every minute
- Two tasks: `rebuild_silver_gold` -> `refresh_match_summary`
- 100% green history

Say: *"In production this would run on MWAA (Managed Workflows for Airflow)."*

---

## 7. Show the code (60 sec)

Open these files, 10 seconds each:
- `src/simulator/match_engine.py` — "the physics engine of cricket"
- `src/producer/match_producer.py` — "23 lines of real Kafka producer"
- `src/ml/train.py` — "trains on 300 simulated matches, ~60 sec"
- `src/genai/sql_agent.py` — "the interesting one — how I stopped
  the LLM from doing anything destructive"
- `airflow/dags/etl_dag.py` — "medallion architecture, self-contained DAG"

---

## 8. The close (30 sec)

> "The whole thing runs on my laptop in Docker, but every component has a
> documented cloud equivalent — see `docs/CLOUD_DEPLOY.md`. Same code,
> swap DuckDB for Snowflake and Kafka for MSK, and you have a
> production-ready fintech-style pipeline."

---

## What if the demo breaks?

- **Kafka not ready** → wait 60 sec after `docker compose up`.
- **No data in dashboard** → check that the consumer terminal is actively
  processing balls; the producer needs to be sending.
- **AI chat fails** → check `.env` has a valid `GEMINI_API_KEY`.
- **Everything nuclear** → `docker compose down -v` + `.\scripts\start_all.ps1`.
