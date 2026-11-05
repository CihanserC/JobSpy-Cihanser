r"""Dubai / Abu Dhabi software developer search, scored against Cihanser's CV.

Run:  .\.venv\Scripts\python.exe my_search\uae_search.py
Output: my_search\results\uae_jobs_<date>.csv (Excel-friendly) + .html
"""

import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from jobspy import scrape_jobs

CITIES = ["Dubai", "Abu Dhabi"]
SEARCH_TERMS = [
    "backend developer",
    "software engineer",
    ".NET developer",
    "Java developer",
    "site reliability engineer",
]
SITES = ["indeed", "linkedin", "bayt"]
HOURS_OLD = 24 * 30  # last month
RESULTS_PER_QUERY = 40

# CV keywords -> weight. Core stack counts more.
CV_KEYWORDS = {
    r"\.net\b|\bc#|asp\.net|dotnet": 3,
    r"\bjava\b|spring\s*boot|\bspring\b": 3,
    r"microservice": 3,
    r"kubernetes|\bk8s\b|openshift": 2,
    r"docker": 1,
    r"kafka|rabbitmq|\bmq\b": 2,
    r"grpc": 2,
    r"\brest\b|restful|api gateway|\bapi\b": 1,
    r"oauth|jwt": 1,
    r"backend|back-end|back end": 2,
    r"\bsre\b|site reliability|observability": 2,
    r"grafana|splunk|dynatrace|\belk\b|elastic": 1,
    r"redis|postgres|sql server|t-sql|\bsql\b": 1,
    r"ci/cd|azure devops|devops": 1,
    r"bank|fintech|financial|payments": 2,
    r"\bpython\b|fastapi": 1,
    r"\brag\b|\bllm\b|vector database": 1,
}
NEGATIVE = r"\bintern\b|internship|junior|graduate|frontend|front-end|ios\b|android|flutter|react native|\bphp\b"

OUT_DIR = Path(__file__).parent / "results"


def score(row) -> int:
    text = f"{row.get('title') or ''} {row.get('description') or ''}".lower()
    s = sum(w for pat, w in CV_KEYWORDS.items() if re.search(pat, text))
    if re.search(NEGATIVE, str(row.get("title") or "").lower()):
        s -= 5
    if re.search(r"senior|lead|sr\.?\b", str(row.get("title") or "").lower()):
        s += 2
    return s


def main() -> None:
    frames = []
    for city in CITIES:
        for term in SEARCH_TERMS:
            print(f"--> {term} @ {city}", flush=True)
            try:
                df = scrape_jobs(
                    site_name=SITES,
                    search_term=term,
                    location=f"{city}, United Arab Emirates",
                    country_indeed="united arab emirates",
                    results_wanted=RESULTS_PER_QUERY,
                    hours_old=HOURS_OLD,
                    fetch_description=True,
                    verbose=0,
                )
            except Exception as e:  # one bad query shouldn't kill the run
                print(f"    failed: {e}", file=sys.stderr)
                continue
            df["query"] = f"{term} @ {city}"
            frames.append(df)
            print(f"    {len(df)} jobs", flush=True)

    if not frames:
        print("No results.")
        return
    jobs = pd.concat(frames, ignore_index=True)
    jobs = jobs.drop_duplicates(subset=["job_url"])
    jobs = jobs.drop_duplicates(subset=["title", "company"])
    jobs["cv_score"] = jobs.apply(score, axis=1)
    jobs = jobs.sort_values(["cv_score", "date_posted"], ascending=[False, False])

    cols = [c for c in ["cv_score", "title", "company", "location", "site",
                        "date_posted", "job_type", "min_amount", "max_amount",
                        "currency", "job_url", "query", "description"] if c in jobs]
    OUT_DIR.mkdir(exist_ok=True)
    stem = OUT_DIR / f"uae_jobs_{date.today():%Y-%m-%d}"
    jobs[cols].to_csv(f"{stem}.csv", index=False, encoding="utf-8-sig")

    html_cols = [c for c in cols if c != "description"]
    html = jobs[html_cols].copy()
    html["job_url"] = html["job_url"].map(lambda u: f'<a href="{u}" target="_blank">open</a>')
    html.to_html(f"{stem}.html", index=False, escape=False)

    print(f"\nTotal unique jobs: {len(jobs)}")
    print(f"Saved: {stem}.csv\n       {stem}.html")
    print(jobs[["cv_score", "title", "company", "site"]].head(25).to_string(index=False))


if __name__ == "__main__":
    main()
