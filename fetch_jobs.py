"""
FSAE Job Tracker — fetch script

Pulls current job postings for every company in companies.json,
compares against the last saved snapshot (docs/jobs.json), and:
  1. Overwrites docs/jobs.json with the current full list (used by the site)
  2. Posts anything NEW since last run to a Discord webhook

Run manually with:  python fetch_jobs.py
Runs automatically via .github/workflows/check-jobs.yml on a schedule.
"""

import html
import re
import json
import os
import sys
from pathlib import Path

import requests

COMPANIES_FILE = Path("companies.json")
JOBS_FILE = Path("docs/jobs.json")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DISCORD_WEBHOOK_URL_2 = os.environ.get("DISCORD_WEBHOOK_URL_2")

HEADERS = {"User-Agent": "FSAE-Job-Tracker/1.0"}

# Only keep postings whose title looks like an internship/co-op/early-career role.
INTERNSHIP_KEYWORDS = [
    "intern", "internship", "co-op", "coop", "college", "university",
    "student", "early career", "new grad", "graduate program","united states","united states of america"
]


def is_internship(title):
    title_lower = title.lower()
    return any(kw in title_lower for kw in INTERNSHIP_KEYWORDS)


def fetch_greenhouse(company):
    """Greenhouse public board API — simple GET, no auth."""
    slug = company["slug"]
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    jobs = []
    for job in data.get("jobs", []):
        jobs.append({
            "id": f"greenhouse:{slug}:{job['id']}",
            "company": company["name"],
            "title": job["title"],
            "location": job.get("location", {}).get("name", "Unknown"),
            "url": job["absolute_url"],
        })
    return jobs


def fetch_workday(company):
    """
    Workday CXS endpoint — POST request, returns paginated JSON.
    tenant/shard/site vary per company; find them by opening the
    company's careers page, watching Network tab for a request to
    *.myworkdayjobs.com/wday/cxs/..., and copying the values from that URL.
    """
    tenant = company["tenant"]
    shard = company["shard"]
    site = company["site"]

    if "VERIFY_ME" in (tenant, site):
        print(f"  [skip] {company['name']}: tenant/site not filled in yet")
        return []

    url = f"https://{tenant}.{shard}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    jobs = []
    offset = 0
    limit = 20

    while True:
        body = {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""}
        resp = requests.post(url, json=body, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        postings = data.get("jobPostings", [])
        if not postings:
            break

        for job in postings:
            jobs.append({
                "id": f"workday:{tenant}:{job.get('bulletFields', [job.get('title', '')])[0] if job.get('bulletFields') else job.get('title', '')}",
                "company": company["name"],
                "title": job.get("title", "Untitled"),
                "location": job.get("locationsText", "Unknown"),
                "url": f"https://{tenant}.{shard}.myworkdayjobs.com{job.get('externalPath', '')}",
            })

        offset += limit
        if offset >= data.get("total", 0):
            break

    return jobs


def fetch_talentbrew(company):
    """
    TalentBrew search API (used by Boeing and others). Returns JSON with a
    "results" key containing an HTML fragment of job listings — we regex
    out the title/link/location/date rather than parsing full HTML, since
    the structure is simple and consistent.
    """
    base_url = company["base_url"].rstrip("/")
    org_id = company["org_id"]
    keywords = company.get("keywords", "intern")

    job_pattern = re.compile(
        r'<a class="search-results__job-link" href="([^"]+)" data-job-id="(\d+)">'
        r'<span class="search-results__job-title">(.*?)</span></a>\s*'
        r'<span class="search-results__job-info location">([^<]*)</span>',
        re.DOTALL,
    )
    total_pages_pattern = re.compile(r'data-total-pages="(\d+)"')

    jobs = []
    page = 1
    total_pages = 1

    while page <= total_pages:
        params = {
            "Keywords": keywords,
            "OrganizationIds": org_id,
            "RecordsPerPage": 15,
            "CurrentPage": page,
        }
        resp = requests.get(f"{base_url}/search-jobs/results", params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        results_html = data.get("results", "")

        if page == 1:
            match = total_pages_pattern.search(results_html)
            if match:
                total_pages = int(match.group(1))

        for href, job_id, title, location in job_pattern.findall(results_html):
            jobs.append({
                "id": f"talentbrew:{org_id}:{job_id}",
                "company": company["name"],
                "title": html.unescape(title).strip(),
                "location": html.unescape(location).strip(),
                "url": f"{base_url}{href}",
            })

        page += 1

    return jobs


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "workday": fetch_workday,
    "talentbrew": fetch_talentbrew,
}


def load_companies():
    with open(COMPANIES_FILE) as f:
        return json.load(f)


def load_previous_jobs():
    if not JOBS_FILE.exists():
        return {}
    with open(JOBS_FILE) as f:
        data = json.load(f)
    return {job["id"]: job for job in data.get("jobs", [])}


def send_discord_alert(job):
    if not DISCORD_WEBHOOK_URL:
        return
    message = {
        "embeds": [{
            "title": f"{job['title']}",
            "description": f"**{job['company']}** — {job['location']}",
            "url": job["url"],
            "color": 3447003,
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=message, timeout=10)
    except requests.RequestException as e:
        print(f"  [warn] Discord post failed for {job['title']}: {e}")


def main():
    companies = load_companies()
    previous_jobs = load_previous_jobs()

    all_jobs = []
    new_jobs = []

    for company in companies:
        ats = company.get("ats")
        fetcher = FETCHERS.get(ats)
        if not fetcher:
            print(f"  [skip] {company['name']}: unknown ATS '{ats}'")
            continue

        print(f"Fetching {company['name']} ({ats})...")
        try:
            jobs = fetcher(company)
        except requests.RequestException as e:
            print(f"  [error] {company['name']}: {e}")
            continue

        jobs = [j for j in jobs if is_internship(j["title"])]
        print(f"  found {len(jobs)} internship/co-op postings")
        all_jobs.extend(jobs)

        for job in jobs:
            if job["id"] not in previous_jobs:
                new_jobs.append(job)

    JOBS_FILE.parent.mkdir(exist_ok=True)
    with open(JOBS_FILE, "w") as f:
        json.dump({"jobs": all_jobs}, f, indent=2)

    print(f"\nTotal postings: {len(all_jobs)}")
    print(f"New since last run: {len(new_jobs)}")

    for job in new_jobs:
        send_discord_alert(job)

    if new_jobs and not DISCORD_WEBHOOK_URL:
        print("  [note] DISCORD_WEBHOOK_URL not set — skipped Discord alerts")


if __name__ == "__main__":
    sys.exit(main())
