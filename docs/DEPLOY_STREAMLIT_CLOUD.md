# Deploy CricketPulse to Streamlit Cloud (free, ~10 minutes)

This gets you a **public URL** anyone can click to see your project working —
perfect for putting on your resume, LinkedIn, and GitHub README.

## What you get
- Live dashboard at `https://your-app-name.streamlit.app`
- Fully functional: pre-loaded match, working ML predictions, Gemini AI chat, "Start Live Match" button
- Free forever (app just sleeps after 7 days of inactivity — one visit wakes it back up in ~30 sec)

---

## Prerequisites (2 min)

- **GitHub account** — https://github.com/join
- **Google Gemini API key** (free) — https://aistudio.google.com/apikey
  1. Sign in with your Google account
  2. Click **Get API key** -> **Create API key** -> **Create API key in new project**
  3. Copy the key that starts with `AIza...`
  4. Keep this browser tab open — you'll paste it later

---

## Step 1 - Push the project to GitHub (3 min)

Open **PowerShell in the project folder** and run these commands one by one:

```powershell
# initialize a git repo
git init
git add .
git commit -m "Initial commit: CricketPulse real-time cricket analytics"

# create a new empty repo on GitHub named 'cricketpulse'
# then paste the URL it gives you into the next command:
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/cricketpulse.git
git push -u origin main
```

**Verify:** open your new GitHub repo in a browser. You should see the project files.

If git asks you to sign in and it fails, install **GitHub Desktop**
(https://desktop.github.com) — click **File -> Add Local Repository**, select
the project folder, then **Publish repository** to GitHub. Same result, zero
typing.

---

## Step 2 - Deploy to Streamlit Cloud (3 min)

1. Go to **https://share.streamlit.io** and sign in with GitHub.
2. Click **"Create app"** -> **"Deploy a public app from GitHub"**.
3. Fill the form:
   - **Repository**: `YOUR_USERNAME/cricketpulse`
   - **Branch**: `main`
   - **Main file path**: `src/dashboard/app.py`
   - **App URL**: pick something short like `cricketpulse` (this becomes `https://cricketpulse.streamlit.app`)
4. Click **"Advanced settings..."** -> **"Secrets"** and paste:

```toml
GEMINI_API_KEY = "AIza-your-key-from-step-0"
GEMINI_MODEL   = "gemini-2.0-flash"
DUCKDB_PATH    = "data/warehouse/cricketpulse.duckdb"
```

5. Click **"Deploy"**.

The first build takes 3-5 minutes (installing pandas, scikit-learn, langchain).
When it finishes, your public URL is live.

---

## Step 3 - Test the deployed app (1 min)

Open your `https://cricketpulse.streamlit.app` URL:

1. You should immediately see the **pre-loaded demo match** (Mumbai Mavericks won by 7 wickets) with all charts, scorecards, and commentary.
2. Type into the chat: **"Who has the highest strike rate?"** -> Gemini answers in ~3 seconds.
3. Open the sidebar (top-left arrow) -> **"Start live match"** -> watch a fresh match stream in real time with live ML predictions.

Done. Copy this URL and put it in:
- Your resume, right next to the project title
- Your LinkedIn projects section
- The top of your GitHub README

---

## Step 4 - Add the live badge to your README

Once deployed, replace the placeholder in your `README.md`:

```markdown
[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://cricketpulse.streamlit.app)
```

Put this line right below the project title in the README.

---

## Troubleshooting

**Build fails with "ModuleNotFoundError"**
- Streamlit Cloud uses `requirements.txt` at the repo root. Make sure that file exists (it does — we already renamed the slim version to `requirements.txt`).

**"GEMINI_API_KEY is not configured"**
- Go to https://share.streamlit.io -> your app -> **Settings** -> **Secrets** -> paste the toml block again. Restart the app from the "..." menu.

**App shows "No match data yet"**
- The bundled `data/warehouse/cricketpulse.duckdb` didn't get pushed. Check with `git ls-files data/warehouse/` in your local repo. If it's missing, run `git add -f data/warehouse/cricketpulse.duckdb && git commit -m "add demo db" && git push`.

**App is slow / times out**
- Free tier has 1 GB RAM. The GradientBoosting models load in ~2 sec on first request. Subsequent requests are instant. If it times out, hit the URL again.

**App has been sleeping**
- Free-tier apps sleep after 7 days of no traffic. First visit takes ~30 sec to wake up. This is normal and mentioned upfront.

---

## Optional: keep the app awake

Free hack: use https://uptimerobot.com (free) to ping your app URL every 5 minutes.
This keeps it warm 24/7 so recruiters never hit a cold-start.

---

## Optional: custom domain

Streamlit Cloud doesn't support custom domains on free tier. Workaround:
buy a cheap domain and use **Cloudflare Page Rules** to forward `cricketpulse.yourname.com` -> `https://cricketpulse.streamlit.app`. Costs ~$10/year for the domain, still free hosting.
