# Resume-ready bullets

Copy-paste any of these under a "Projects" section. Each one is designed to
survive the 6-second recruiter scan.

---

## Standard (3 lines, ATS-friendly)

**CricketPulse — Real-Time Cricket Analytics with GenAI** *(Python, Kafka, Airflow, DuckDB, scikit-learn, LangChain, Gemini, Streamlit, Docker)*
- Built an end-to-end streaming pipeline: ball-by-ball match simulator -> **Apache Kafka** -> Python consumer -> **DuckDB medallion warehouse** (bronze/silver/gold), orchestrated by **Airflow** with a 1-minute ETL DAG.
- Trained a **GradientBoosting classifier** to predict per-ball win probability (72.8% acc, Brier 0.17) and a regressor for innings final score (MAE 10.4 runs); served real-time inference on every incoming ball.
- Built a **LangChain + Gemini text-to-SQL agent** over the warehouse and a **Streamlit** dashboard with live win-probability chart, scorecards, AI expert commentary, and a natural-language chat.

## Compact (2 lines, for cramped resumes)

**CricketPulse — Real-Time IPL Analytics + AI Commentator** *(Kafka, Airflow, DuckDB, scikit-learn, LangChain, Gemini, Streamlit, Docker)*
- Streaming pipeline that ingests ball-by-ball events into a medallion DuckDB warehouse, predicts win probability with a GradientBoosting model (72.8% acc), and exposes a Gemini-powered text-to-SQL chat + live Streamlit dashboard — full Docker Compose stack, one-command startup.

## LinkedIn "About the project" (paragraph)

Designed and built a production-grade real-time analytics platform that
combines **data engineering, machine learning, and generative AI** in a
single project. A synthetic ball-by-ball IPL match simulator streams
events through **Apache Kafka**; a Python consumer lands them into a
**DuckDB warehouse** organized as a bronze/silver/gold medallion, refreshed
every minute by an **Apache Airflow** DAG. A gradient-boosting classifier
predicts per-ball win probability (72.8% test accuracy, Brier 0.17), and a
regressor forecasts the innings final total. The frontend is a **Streamlit**
dashboard with live scorecards, a win-probability chart, and an AI
"expert take" that regenerates every three seconds. The centerpiece is a
**LangChain + Google Gemini text-to-SQL agent** that lets any user ask
questions like *"Which bowler has been the most economical this match?"*
in plain English — the LLM writes a read-only DuckDB query, executes it,
and rephrases the result. All infrastructure is Dockerized and every
component has a documented AWS migration path (MSK, MWAA, ECS, Snowflake).

## Interview one-liner

> "It's a real-time streaming platform that predicts IPL win probability
> after every ball and lets you chat with the match data in plain English."

---

## Talking points if asked *"why is this project impressive?"*

1. **Every layer of a modern data stack**: streaming, batch, warehouse
   modeling, ML training + serving, LLM orchestration, dashboards.
2. **The medallion architecture is real**: bronze -> silver -> gold with a
   clean separation between raw, cleaned, and business-ready data.
3. **The GenAI is safe**: SQL sandbox blocks non-SELECT queries; the LLM
   never sees writable connections. This is what "productionizing LLMs"
   actually means.
4. **The ML is calibrated, not just "trained"**: I report Brier score,
   not just accuracy, because a 72% classifier that says "50-50" on
   easy matches is worse than a 65% classifier that's honest.
5. **It's Dockerized end-to-end**: one command starts Kafka, Zookeeper,
   Kafka UI, Airflow (webserver + scheduler + postgres). Same skills you
   need to deploy to ECS.
6. **The domain is memorable**: recruiters remember "the guy who built
   the AI cricket commentator" — nobody remembers the 400th churn project.

---

## Skills demonstrated (bullet-list for a Skills section)

- **Streaming**: Apache Kafka, producer/consumer APIs, partitioning
- **Orchestration**: Apache Airflow, DAG design, PythonOperator
- **Warehousing**: Medallion architecture, DuckDB, star-schema aggregations
- **ML**: scikit-learn pipelines, GradientBoosting, probability calibration
- **GenAI**: LangChain, Google Gemini, prompt engineering, text-to-SQL, RAG-like grounding
- **Dashboards**: Streamlit, Plotly, real-time refresh
- **DevOps**: Docker Compose, healthchecks, one-command startup
- **Cloud-ready**: documented migration to AWS MSK / MWAA / Snowflake / ECS
