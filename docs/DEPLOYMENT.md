# Deployment guide - Streamlit Community Cloud

The app is a standard Streamlit project: entry point `streamlit_app.py`, dependencies in `requirements.txt`,
data in `data/` loaded with relative paths. It needs no secrets, database or API keys.

## 1. Put the project on GitHub

The repository must contain the whole `rr-pressure-analytics` folder **as the repository root**
(so `streamlit_app.py` sits at the top level). `data/ball_by_ball.csv` is 41 MB: that is fine for a git push
(GitHub's per-file limit is 100 MB) but too large for GitHub's drag-and-drop web upload (25 MB limit), so use
git or GitHub Desktop.

**With GitHub Desktop**

1. *File > Add local repository* and choose the `rr-pressure-analytics` folder.
2. Click *Publish repository*. Choose a name (e.g. `rr-pressure-analytics`). Untick *Keep this code private* if you
   want a public repo (Community Cloud also supports private repos once you grant access).

**With the git command line**

```bash
cd rr-pressure-analytics
git init -b main
git add .
git commit -m "Rajasthan Royals pressure analytics dashboard"
git remote add origin https://github.com/<your-user>/rr-pressure-analytics.git
git push -u origin main
```

## 2. Deploy on Streamlit Community Cloud

1. Sign in at https://share.streamlit.io with your GitHub account and authorise Streamlit.
2. Click *Create app* > *Deploy a public app from GitHub* (or *Yup, I have an app*).
3. Fill in:
   - Repository: `<your-user>/rr-pressure-analytics`
   - Branch: `main`
   - Main file path: `streamlit_app.py`
   - App URL: pick a subdomain, e.g. `rr-pressure-analytics`
4. *Advanced settings* > Python version: **3.12** (anything 3.11+ works).
5. Click *Deploy*. The first build installs dependencies (1-3 minutes). The first page load then tags every
   delivery (a few seconds); later loads are cached.

The public URL looks like `https://<subdomain>.streamlit.app`.

## 3. Updating

Commit and push to `main`; Community Cloud redeploys automatically. After changing data or analytics code, run
`python scripts/validate.py` locally and commit the regenerated `docs/DATA_VALIDATION.md`.

## 4. Troubleshooting

| Symptom | Fix |
|---|---|
| "Missing data files in data/" | The `data/` folder was not committed. Check it is in the repo. |
| `ModuleNotFoundError: src` | The repo root is the parent folder. Make `rr-pressure-analytics` the root, or set *Main file path* to `rr-pressure-analytics/streamlit_app.py`. |
| Build fails on pandas | Select Python 3.11 or 3.12 in Advanced settings. |
| App sleeps | Free apps sleep after inactivity; the first visitor wakes them (about 30 s). |

## Alternative hosts

Any platform that runs Python can host the app with the same command:

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py --server.port $PORT --server.address 0.0.0.0
```

(e.g. Render, Railway, Hugging Face Spaces with the Streamlit SDK, or a Docker container.)
