# FSAE Job Tracker

Tracks early-career/internship openings at motorsports, space, defense, and
auto companies. Runs on a schedule for free via GitHub Actions — no server,
no database, no hosting bill.

## How it works
1. `fetch_jobs.py` reads `companies.json`, pulls current postings from each
   company's ATS (Greenhouse or Workday), and writes the results to
   `docs/jobs.json`.
2. Anything new since the last run gets posted to a Discord webhook.
3. `docs/index.html` is a static page (served via GitHub Pages) that reads
   `docs/jobs.json` and lets people filter by title, company, and location.
4. `.github/workflows/check-jobs.yml` runs step 1 automatically every 3
   hours and commits the updated `jobs.json`.

## One-time setup

### 1. Push this to GitHub
```bash
cd fsae-job-tracker
git init
git add .
git commit -m "Initial scaffold"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/fsae-job-tracker.git
git push -u origin main
```

### 2. Turn on GitHub Pages
Repo → **Settings** → **Pages** → Source: `Deploy from a branch` → Branch:
`main`, folder: `/docs` → Save. Your site will be live at
`https://YOUR_USERNAME.github.io/fsae-job-tracker/` within a minute or two.

### 3. Add the Discord webhook
- In your Discord server: channel settings → **Integrations** → **Webhooks**
  → **New Webhook** → copy the URL.
- In the GitHub repo: **Settings** → **Secrets and variables** → **Actions**
  → **New repository secret** → name it `DISCORD_WEBHOOK_URL`, paste the URL.

### 4. Fill in the Workday companies
`companies.json` has placeholder `"VERIFY_ME"` values for every Workday
company (Ford, GM, Boeing, Lockheed, etc.) — Workday doesn't have one
predictable URL pattern like Greenhouse does, so each company's
`tenant`/`shard`/`site` needs to be found manually once:

1. Open the company's careers page and search for a job.
2. Open your browser's dev tools → **Network** tab.
3. Look for a request to `something.wdX.myworkdayjobs.com/wday/cxs/...`
4. From that URL, `something` before `.wd` is the **tenant**, `wdX` is the
   **shard**, and the last path segment before `/jobs` is the **site**.

Example: `ford.wd1.myworkdayjobs.com/wday/cxs/ford/Ford_Careers/jobs` →
tenant: `ford`, shard: `wd1`, site: `Ford_Careers`.

Until a company's fields are filled in, the script just skips it (prints a
`[skip]` line) rather than failing.

### 5. Test it locally (optional but recommended)
```bash
pip install -r requirements.txt
python fetch_jobs.py
```
This writes `docs/jobs.json` — open `docs/index.html` in a browser to check
it renders.

## Adding a company later
Open `companies.json` and add an entry:

**Greenhouse:**
```json
{ "name": "Company Name", "ats": "greenhouse", "slug": "company-slug" }
```
The slug is in the company's Greenhouse URL: `boards.greenhouse.io/SLUG`.

**Workday:** follow the tenant/shard/site steps above.

Commit and push — the next scheduled run (or a manual trigger from the
**Actions** tab → "Check job postings" → **Run workflow**) will pick it up.
No code changes required.

## Companies included at launch
**Confirmed working (Greenhouse):** SpaceX, Rocket Lab
**Workday (need slugs filled in):** Ford, GM, Boeing, Lockheed Martin,
Northrop Grumman, General Dynamics, General Electric, Honda, Toyota, Blue
Origin, ULA, Amazon

**Not yet supported** (no confirmed public ATS — likely need a
company-specific scraper if added later): Ferrari, Team Penske, Hendrick
Motorsports, Toyota Gazoo Racing, Wayne Taylor Racing, Mazda
