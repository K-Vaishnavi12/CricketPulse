# CricketPulse — Your Personal Deployment Cheat Sheet

**GitHub username:** `K-Vaishnavi12`
**Repo name:** `cricketpulse`
**Target public URL:** `https://cricketpulse-vaishnavi.streamlit.app` (or pick any subdomain when deploying)

---

## Step 1 — Rotate the Gemini key first (you already exposed the old one)

1. Go to https://aistudio.google.com/apikey
2. **Delete** the key you shared publicly
3. Click **Create API key** → copy the new one
4. Paste it into `.env` (replace `PASTE_YOUR_NEW_KEY_HERE`)

---

## Step 2 — Create the GitHub repo (browser, 30 seconds)

1. Open https://github.com/new
2. **Repository name**: `cricketpulse`
3. **Description**: `Real-time IPL win-probability + AI commentator (Kafka, Airflow, DuckDB, scikit-learn, LangChain, Gemini, Streamlit, Docker)`
4. **Public** (required for free Streamlit Cloud)
5. **DO NOT** check "Add a README" or ".gitignore" — the project already has them
6. Click **Create repository**

---

## Step 3 — Push the project (PowerShell in the project folder)

Copy-paste this whole block into your terminal:

```powershell
git init
git add .
git commit -m "Initial commit: CricketPulse - real-time cricket analytics with Kafka, ML, and GenAI"
git branch -M main
git remote add origin https://github.com/K-Vaishnavi12/cricketpulse.git
git push -u origin main
```

If Git asks for credentials, use your GitHub username and a **Personal Access Token** as the password (NOT your GitHub password):
- Get token: https://github.com/settings/tokens → **Generate new token (classic)** → tick `repo` scope → **Generate** → copy the `ghp_...` string → paste as password.

**Or use GitHub Desktop:** https://desktop.github.com (easier — Add Local Repository → Publish).

---

## Step 4 — Deploy to Streamlit Cloud

1. Go to https://share.streamlit.io
2. Sign in with GitHub (grant access to `cricketpulse` repo)
3. Click **Create app** → **Deploy a public app from GitHub**
4. Fill in:
   - **Repository**: `K-Vaishnavi12/cricketpulse`
   - **Branch**: `main`
   - **Main file path**: `src/dashboard/app.py`
   - **App URL**: `cricketpulse-vaishnavi` (or `k-vaishnavi-cricketpulse`, or whatever's available)
5. Click **Advanced settings** → **Secrets**, paste:

```toml
GEMINI_API_KEY = "AIza..."   # your NEW rotated key
GEMINI_MODEL   = "gemini-2.0-flash"
DUCKDB_PATH    = "data/warehouse/cricketpulse.duckdb"
```

6. Click **Deploy**

First build takes 3-5 min (installing pandas, scikit-learn, langchain, etc.).

---

## Step 5 — After deployment

Once live, update the README with your actual URL:

Edit `README.md` line 5 — replace `https://cricketpulse.streamlit.app` with your real URL. Then:

```powershell
git add README.md
git commit -m "docs: add live demo URL"
git push
```

Streamlit auto-redeploys in ~30 seconds.

---

## Step 6 — Post on LinkedIn (the recruiter magnet)

Copy this post:

> Just shipped **CricketPulse** — a real-time cricket analytics platform that streams ball-by-ball match data through Kafka, predicts win probability with a gradient-boosting model (72.8% accuracy), and lets you chat with the match data using Google Gemini.
>
> 🔴 Live demo: https://cricketpulse-vaishnavi.streamlit.app
> 💻 Code: https://github.com/K-Vaishnavi12/cricketpulse
>
> Tech stack: Python, Apache Kafka, Apache Airflow, DuckDB, scikit-learn, LangChain, Google Gemini, Streamlit, Docker.
>
> One project. Every layer of a modern data stack. Built for placement season.
>
> #DataEngineering #MachineLearning #GenAI #Python

---

## Troubleshooting

- **`fatal: remote origin already exists`** → run `git remote remove origin` first, then retry step 3
- **`Permission denied (publickey)`** → use the HTTPS URL as shown (not SSH); token in place of password
- **Streamlit build fails "No module named X"** → make sure `requirements.txt` (the slim one) is committed
- **App shows "No match data yet"** → the DuckDB file wasn't committed; run `git add -f data/warehouse/cricketpulse.duckdb && git commit -m "add demo db" && git push`
