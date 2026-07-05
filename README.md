# CricketPulse — Real-Time IPL Win-Probability & AI Commentator

> An end-to-end real-time data pipeline that streams ball-by-ball cricket events, predicts win probability with ML, and answers business questions with GenAI — like an AI cricket analyst you can talk to.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://cricketpulse.streamlit.app)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Live demo:** https://cricketpulse.streamlit.app (replace with your URL after deployment)

Built to demonstrate **Data Engineering + Machine Learning + Generative AI + Cloud-ready architecture** in a single project.

---

## Why this project stands out

Most placement portfolios have the same 3 projects: churn prediction, stock analyzer, sales dashboard. This one is different:

- **Instantly memorable** to Indian recruiters — everyone follows IPL.
- Same production-grade tech stack as a "boring" e-commerce pipeline, but with a story people actually remember after the interview.
- Combines **streaming + batch + ML + LLM + dashboards** — the exact skill combo companies pay for in 2026.

---

## Architecture

```
                         +-----------------------------+
                         |   Ball-by-Ball Simulator    |
                         |  (realistic IPL match gen)  |
                         +--------------+--------------+
                                        |
                                        v
                          +---------------------------+
                          |   Kafka Topic: balls.raw  |
                          +-------------+-------------+
                                        |
                    +-------------------+-------------------+
                    |                                       |
                    v                                       v
        +------------------------+           +----------------------------+
        |  Consumer -> DuckDB    |           |  Real-Time Inference       |
        |  (bronze raw events)   |           |  (win-prob per ball)       |
        +-----------+------------+           +--------------+-------------+
                    |                                       |
                    v                                       v
        +------------------------+           +----------------------------+
        |  Airflow DAG            |           |  Kafka Topic: predictions  |
        |  bronze -> silver ->    |           +--------------+-------------+
        |  gold (star schema)     |                          |
        +-----------+------------+                          v
                    |                        +----------------------------+
                    v                        |    Streamlit Dashboard     |
        +------------------------+           |  * Live scorecard          |
        |  DuckDB Warehouse       |<---------|  * Win-probability chart   |
        |  (silver + gold)        |          |  * AI commentary feed      |
        +-----------+------------+           |  * Chat: ask any question  |
                    |                        +--------------+-------------+
                    v                                       ^
        +------------------------+                          |
        |  GenAI Layer            |--------------------------+
        |  LangChain + Gemini     |
        |  * text-to-SQL          |
        |  * AI commentator       |
        +------------------------+
```

---

## Tech Stack (all free)

| Layer                | Tech                                              |
| -------------------- | ------------------------------------------------- |
| **Streaming**        | Apache Kafka + Zookeeper (Docker)                 |
| **Orchestration**    | Apache Airflow (Docker)                           |
| **Warehouse**        | DuckDB (Snowflake-compatible SQL, zero setup)     |
| **ML**               | scikit-learn (logistic regression + gradient boost) |
| **GenAI**            | LangChain + Google Gemini (free API tier)         |
| **Dashboard**        | Streamlit + Plotly                                |
| **Language**         | Python 3.11                                       |
| **Containerization** | Docker Compose                                    |
| **Cloud-ready**      | Swap DuckDB -> Snowflake, Kafka -> MSK, Streamlit -> ECS (docs included) |

---

## Quick Start (5 minutes)

### Prerequisites
- Docker Desktop running
- Python 3.11+
- A free Google Gemini API key -> https://aistudio.google.com/apikey

### 1. Clone & configure
```powershell
cp .env.example .env
# Open .env and paste your GEMINI_API_KEY
```

### 2. Install Python deps
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Start infrastructure (Kafka + Airflow)
```powershell
docker compose -f docker/docker-compose.yml up -d
```
Wait ~60 seconds for Kafka to be ready.

### 4. Bootstrap the warehouse + train ML models
```powershell
python scripts/bootstrap.py
```
This creates DuckDB schemas, seeds historical matches, and trains the win-probability model.

### 5. Start the live pipeline (3 terminals)
```powershell
# Terminal 1 - producer (simulates a live match)
python -m src.producer.match_producer

# Terminal 2 - consumer (writes to warehouse + scores predictions)
python -m src.consumer.ball_consumer

# Terminal 3 - dashboard
streamlit run src/dashboard/app.py
```

Open http://localhost:8501 -> watch the match unfold in real time and chat with the AI analyst.

### 6. Airflow UI
Open http://localhost:8080 (user: `admin`, pass: `admin`) to see the ETL DAG running every minute.

---

## Deploy your own live demo (free, 10 min)

Want your own public URL to share with recruiters? See **[docs/DEPLOY_STREAMLIT_CLOUD.md](docs/DEPLOY_STREAMLIT_CLOUD.md)** — a step-by-step guide to deploy to Streamlit Community Cloud for free:

```
Push to GitHub  ->  Streamlit Cloud detects it  ->  Paste GEMINI_API_KEY  ->  Live URL
```

The deployed app runs the simulator + ML + Gemini chat entirely in-browser (no Kafka/Airflow needed for the public demo — those still run locally for the full pipeline story).

---

## Demo Questions to Ask the AI

Type these into the dashboard chat box during a live match:

- *"Who has the highest strike rate in this match so far?"*
- *"What is CSK's win probability trend in the last 5 overs?"*
- *"Which bowler has been most economical?"*
- *"Predict the final score if the current run rate continues."*
- *"Why is MI losing this match?"*

The LLM converts your question -> SQL -> queries the warehouse -> explains the answer in English.

---

## Project Structure

```
.
|-- docker/                 Docker Compose for Kafka + Airflow
|-- airflow/dags/           ETL DAG (bronze -> silver -> gold)
|-- src/
|   |-- simulator/          Realistic ball-by-ball match generator
|   |-- producer/           Streams balls to Kafka
|   |-- consumer/           Kafka -> DuckDB + real-time inference
|   |-- warehouse/          DuckDB schema + SQL transformations
|   |-- ml/                 Training + inference for win-prob & runs models
|   |-- genai/              LangChain agents (text-to-SQL + commentator)
|   |-- dashboard/          Streamlit UI
|   `-- common/             Shared config, logging, schemas
|-- models/                 Trained .pkl artifacts
|-- data/                   DuckDB file + seed CSVs
|-- scripts/                bootstrap, seed, smoke tests
|-- tests/                  Unit + integration tests
`-- requirements.txt
```

---

## What each component demonstrates (for your resume / interview)

| Skill                       | Where in the project                                        |
| --------------------------- | ----------------------------------------------------------- |
| Kafka streaming             | `src/producer`, `src/consumer`, `docker/docker-compose.yml` |
| Airflow orchestration       | `airflow/dags/etl_dag.py`                                   |
| Data warehouse modeling     | `src/warehouse/schema.sql` (medallion: bronze/silver/gold)  |
| Feature engineering         | `src/ml/features.py`                                        |
| ML model training + serving | `src/ml/train.py`, `src/ml/inference.py`                    |
| RAG / text-to-SQL           | `src/genai/sql_agent.py`                                    |
| LLM prompt engineering      | `src/genai/commentator.py`                                  |
| Real-time dashboards        | `src/dashboard/app.py`                                      |
| Docker / infra as code      | `docker/docker-compose.yml`                                 |
| Cloud migration path        | `docs/CLOUD_DEPLOY.md`                                      |

---

## Cloud Deployment Path (optional)

See `docs/CLOUD_DEPLOY.md` for how to migrate this exact codebase to:
- **Snowflake** (replace DuckDB, change 3 lines)
- **AWS MSK** (managed Kafka)
- **AWS ECS + Fargate** (host the dashboard)
- **Airflow on MWAA** or **Google Cloud Composer**

---

## License
MIT
