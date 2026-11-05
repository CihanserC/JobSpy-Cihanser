r"""JobSpy web UI.

Run:  .\.venv\Scripts\streamlit.exe run my_search\app.py
"""

import re
from datetime import date

import pandas as pd
import streamlit as st

from jobspy import scrape_jobs
from uae_search import CV_KEYWORDS, NEGATIVE

SITE_OPTIONS = ["indeed", "linkedin", "bayt", "glassdoor", "google"]
DEFAULT_TERMS = "backend developer\nsoftware engineer\n.NET developer\nJava developer\nsite reliability engineer"
DEFAULT_KEYWORDS = "\n".join(f"{w} | {p}" for p, w in CV_KEYWORDS.items())

st.set_page_config(page_title="JobSpy Search", page_icon="🔎", layout="wide")
st.title("🔎 JobSpy iş arama")


def parse_keywords(text: str) -> dict[str, int]:
    out = {}
    for line in text.splitlines():
        if "|" not in line:
            continue
        w, pat = line.split("|", 1)
        try:
            re.compile(pat.strip())
            out[pat.strip()] = int(w.strip())
        except (ValueError, re.error):
            st.sidebar.warning(f"Geçersiz satır atlandı: {line}")
    return out


def score(row, keywords: dict[str, int], negative: str) -> int:
    title = str(row.get("title") or "").lower()
    text = f"{title} {row.get('description') or ''}".lower()
    s = sum(w for pat, w in keywords.items() if re.search(pat, text))
    if negative and re.search(negative, title):
        s -= 5
    if re.search(r"senior|lead|sr\.?\b", title):
        s += 2
    return s


with st.sidebar:
    st.header("Arama")
    terms = st.text_area("Arama terimleri (her satır bir sorgu)", DEFAULT_TERMS, height=140)
    cities = st.text_area("Şehirler (her satır)", "Dubai\nAbu Dhabi", height=70)
    country = st.text_input("Ülke", "United Arab Emirates")
    sites = st.multiselect("Siteler", SITE_OPTIONS, default=["indeed", "linkedin", "bayt"])
    days = st.slider("En fazla kaç günlük ilan", 1, 60, 30)
    per_query = st.slider("Sorgu başına sonuç", 10, 100, 40, step=10)
    fetch_desc = st.checkbox("İlan açıklamalarını çek (puanlama için, daha yavaş)", True)
    remote = st.checkbox("Sadece remote", False)
    proxy = st.text_input("Proxy (opsiyonel, user:pass@host:port)", "")

    with st.expander("CV puanlama ayarları"):
        kw_text = st.text_area("ağırlık | regex", DEFAULT_KEYWORDS, height=300)
        negative = st.text_input("Başlıkta varsa -5 (regex)", NEGATIVE)

    run = st.button("Ara", type="primary", use_container_width=True)

if run:
    term_list = [t.strip() for t in terms.splitlines() if t.strip()]
    city_list = [c.strip() for c in cities.splitlines() if c.strip()] or [""]
    if not term_list or not sites:
        st.error("En az bir arama terimi ve bir site seç.")
        st.stop()

    queries = [(t, c) for c in city_list for t in term_list]
    bar = st.progress(0.0)
    status = st.empty()
    frames, errors = [], []
    for i, (term, city) in enumerate(queries, 1):
        loc = f"{city}, {country}" if city else country
        status.write(f"**{i}/{len(queries)}** — {term} @ {loc}")
        try:
            df = scrape_jobs(
                site_name=sites,
                search_term=term,
                location=loc,
                country_indeed=country.lower(),
                results_wanted=per_query,
                hours_old=days * 24,
                fetch_description=fetch_desc,
                is_remote=remote,
                proxies=proxy or None,
                verbose=0,
            )
            df["query"] = f"{term} @ {city}"
            frames.append(df)
        except Exception as e:
            errors.append(f"{term} @ {loc}: {e}")
        bar.progress(i / len(queries))
    status.empty()
    for err in errors:
        st.warning(err)

    if frames:
        jobs = pd.concat(frames, ignore_index=True)
        jobs = jobs.drop_duplicates(subset=["job_url"]).drop_duplicates(subset=["title", "company"])
        kw = parse_keywords(kw_text)
        jobs["cv_score"] = jobs.apply(score, axis=1, keywords=kw, negative=negative)
        jobs = jobs.sort_values(["cv_score", "date_posted"], ascending=[False, False])
        st.session_state["jobs"] = jobs.reset_index(drop=True)
    else:
        st.session_state.pop("jobs", None)
        st.info("Sonuç bulunamadı.")

jobs = st.session_state.get("jobs")
if jobs is not None:
    st.subheader(f"{len(jobs)} benzersiz ilan")

    c1, c2, c3 = st.columns(3)
    min_score = c1.slider("Min CV puanı", int(jobs["cv_score"].min()), int(jobs["cv_score"].max()), 0)
    site_filter = c2.multiselect("Site filtresi", sorted(jobs["site"].dropna().unique()))
    text_filter = c3.text_input("Başlık / şirket içinde ara")

    view = jobs[jobs["cv_score"] >= min_score]
    if site_filter:
        view = view[view["site"].isin(site_filter)]
    if text_filter:
        mask = (view["title"].fillna("") + " " + view["company"].fillna("")).str.contains(
            text_filter, case=False, regex=False)
        view = view[mask]

    cols = [c for c in ["cv_score", "title", "company", "location", "site", "date_posted",
                        "min_amount", "max_amount", "currency", "job_url"] if c in view]
    event = st.dataframe(
        view[cols],
        use_container_width=True,
        hide_index=True,
        height=520,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "cv_score": st.column_config.ProgressColumn(
                "CV puanı", min_value=0, max_value=max(int(jobs["cv_score"].max()), 1), format="%d"),
            "job_url": st.column_config.LinkColumn("Link", display_text="aç"),
            "date_posted": st.column_config.DateColumn("Tarih"),
        },
    )

    st.download_button(
        "CSV indir",
        view.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"jobs_{date.today():%Y-%m-%d}.csv",
        mime="text/csv",
    )

    rows = event.selection.rows if event and event.selection else []
    if rows:
        job = view.iloc[rows[0]]
        st.divider()
        st.markdown(f"### {job['title']} — {job['company']}")
        st.caption(f"{job.get('location', '')} · {job['site']} · puan {job['cv_score']}")
        st.link_button("İlana git", job["job_url"])
        desc = job.get("description")
        st.markdown(desc if isinstance(desc, str) and desc else "_Açıklama yok._")
    else:
        st.caption("Açıklamayı görmek için tablodan bir satır seç.")
