# AusFlash — News Pipeline v2

> **Global news. Australian speed.**

AusFlash is an end-to-end news intelligence pipeline inspired by [InShorts](https://inshorts.com) (India) — built for Australia. It scrapes global news sources, filters out stale and duplicate stories, classifies articles into sections, and summarises each one to ≤60 words using open-source AI models. The output is a clean, structured CSV ready for any downstream use: a web app, a dashboard, a newsletter, or further analysis.

---

## The Idea

Most news apps show you 30 tabs of the same story with different headlines. AusFlash fixes that:

1. **Scrape** — pull articles from 20+ global sources (BBC, Al Jazeera, NYT, CNBC, TechCrunch, etc.) via Apify, which handles proxies, Cloudflare bypass, and rate limiting
2. **Filter** — drop stale articles (>48 hours old), bad URLs, promo pages, and articles with no content
3. **Deduplicate** — remove exact duplicates by title, then near-duplicates using TF-IDF cosine similarity
4. **Classify** — assign each article to one of 9 sections (Tech, Politics, Business, Crime, Science, Sport, Entertainment, Lifestyle, World) using keyword matching — no API call needed
5. **Summarise** — compress each article's description to ≤60 words using BART (open-source, runs locally)
6. **Export** — save to CSV with all metadata for use in any app or analysis

---

## Pipeline Overview

```
Apify Actor (100+ global sources)
        ↓
Content filter — bad URLs, promo pages, missing description
        ↓
48-hour date filter — drop anything older than 2 days
        ↓
Exact title deduplication
        ↓
Similarity deduplication — TF-IDF cosine ≥ 0.70
        ↓
Section classification — keyword matching, 9 sections
        ↓
smart_news_raw.csv
        ↓
BART summariser — ≤60 words per article
        ↓
smart_news_summarised.csv
```

---

## Notebooks

| # | File | Purpose | Output |
|---|------|---------|--------|
| 1 | `1_scrape_news_apify.ipynb` | Scrape, filter, dedup, classify | `smart_news_raw.csv` |
| 2 | `2_summarise_csv.ipynb` | Summarise each article to ≤60 words | `smart_news_summarised.csv` |
| 3 | `3_model_evaluation.ipynb` | Compare BART vs DistilBART vs PEGASUS | `model_comparison.csv` |
| 4 | `4_automation_apify.ipynb` | Real-time pipeline — runs every 30 min | `smart_news_live.csv` |

Run **1 → 2** for a one-shot scrape and summarise.  
Run **4** alone for a continuous live feed (includes summarisation).  
Run **3** anytime to benchmark which model suits your hardware.

---

## Quick Start

### 1. Install dependencies

```bash
pip install apify-client pandas scikit-learn python-dateutil transformers torch sentencepiece schedule
```

### 2. Get an Apify API token

1. Create a free account at [apify.com](https://apify.com)
2. Go to [console.apify.com/settings/integrations](https://console.apify.com/settings/integrations)
3. Copy your API token

### 3. Add your token

Open `1_scrape_news_apify.ipynb` and `4_automation_apify.ipynb` and paste your token:

```python
APIFY_API_TOKEN = 'YOUR_APIFY_API_TOKEN_HERE'
```

### 4. Run

```
Notebook 1  →  smart_news_raw.csv        (scrape + classify)
Notebook 2  →  smart_news_summarised.csv  (add AI summaries)
Notebook 4  →  smart_news_live.csv        (continuous, every 30 min)
```

---

## Why Apify?

Direct scraping of news sites like ABC AU, Guardian AU, and BBC runs into Cloudflare blocks and IP bans within minutes. Apify runs on managed infrastructure with rotating proxies — no IP bans, no HTML parsing maintenance, no robots.txt issues. The actor used is `complex_intricate_networks/news-article-scraper-100-global-sources-api`, which supports 100+ global sources and returns structured `source`, `title`, `description`, `url`, and `published_at` fields.

---

## Verified Sources (live-tested May 2026)

These sources return current articles consistently:

| Source | Avg articles/run | Notes |
|--------|-----------------|-------|
| BBC World News | ~35 | Reliable, current |
| Al Jazeera | ~25 | Reliable, current |
| CNBC | ~30 | Reliable, current |
| The New York Times | ~20 | Reliable, current |
| TechCrunch | ~20 | Reliable, current |
| Wired | ~65 | Promo pages auto-filtered |
| Variety | ~10 | Reliable, current |
| The Guardian World News | ~15 | Reliable, current |
| Business Insider | ~15 | Reliable |
| Mashable | ~10 | Reliable |
| Rolling Stone | ~10 | Reliable |
| Vox | ~10 | Reliable |
| TIME | ~10 | Reliable |
| Ars Technica | ~15 | Reliable |
| CNET News | ~15 | Reliable |
| CBS News | ~15 | Reliable |
| CoinDesk | ~10 | Reliable |

**Do not use — confirmed stale in live tests:**

| Source | Issue |
|--------|-------|
| CNN | Returns April 2023 articles |
| WSJ World News | Returns January 2025 articles |
| Forbes | Returns January 2024 articles |
| Bloomberg, Financial Times, The Economist | Paywalled — returns 0 articles |

---

## Pipeline Features

### 48-Hour Date Filter

Every article's `published_at` timestamp is parsed to UTC and its age in hours is calculated. Anything older than 48 hours is dropped. Articles with no date are also dropped (treated as 9999h old).

```python
MAX_AGE_HOURS = 48  # Adjust in config
```

### Similarity Deduplication

TF-IDF cosine similarity is computed on `title + description`. Any two articles with similarity ≥ 0.70 are treated as near-duplicates — the earlier article is kept, the later one is dropped. This runs after exact title dedup.

```python
SIMILARITY_THRESHOLD = 0.70  # Lower = stricter, Higher = looser
```

### Section Classification

Rule-based keyword matching on `title + description`. No API call. Runs in milliseconds.

| Priority | Section | Example keywords |
|----------|---------|-----------------|
| 1 | Crime | arrested, murder, trial, fraud, shooting, prison |
| 2 | Tech | ai, google, apple, hack, chip, smartphone, chatgpt |
| 3 | Politics | election, parliament, trump, minister, vote, nato |
| 4 | Business | stock, inflation, layoff, crypto, bitcoin, earnings |
| 5 | Science | nasa, climate, vaccine, outbreak, species, volcano |
| 6 | Sport | nrl, afl, f1, cricket, nba, championship, motogp |
| 7 | Entertainment | netflix, oscar, album, concert, celebrity, bafta |
| 8 | Lifestyle | recipe, travel, wellness, fitness, parenting, dating |
| 9 | World | war, ceasefire, refugee, ukraine, iran, disaster |

World is the fallback — any article that doesn't match a more specific section lands here. First match wins when multiple sections apply.

---

## CSV Output Columns

| Column | Description |
|--------|-------------|
| `website_name` | Source publication |
| `section` | One of 9 news sections |
| `title` | Article headline |
| `ai_summary` | ≤60-word AI-generated summary |
| `description` | Original description from Apify |
| `url` | Full article URL |
| `published_at` | Publication datetime (UTC) |
| `age_hours` | Hours since publication at scrape time |
| `scrape_time` | Time of scrape (HH:MM:SS) |

---

## Summarisation Models

All models run locally — no API key needed.

| Model | HuggingFace ID | Size | Best for |
|-------|---------------|------|---------|
| BART Large CNN | `facebook/bart-large-cnn` | ~1.6 GB | Best quality |
| DistilBART | `sshleifer/distilbart-cnn-12-6` | ~300 MB | Fast, CPU-friendly |
| PEGASUS | `google/pegasus-cnn_dailymail` | ~2.3 GB | Abstractive summaries |

Notebook 4 (automation) uses **DistilBART** by default for speed.  
Notebook 2 uses **BART Large CNN** for best quality.  
Switch via `MODEL_NAME` in the config cell of any notebook.

---

## Configuration Reference

All tunable settings are in the `# CONFIG` cell at the top of each notebook:

| Setting | Default | Description |
|---------|---------|-------------|
| `APIFY_API_TOKEN` | `'YOUR_TOKEN'` | Your Apify API key |
| `MAX_AGE_HOURS` | `48` | Drop articles older than this |
| `SIMILARITY_THRESHOLD` | `0.70` | Cosine similarity cutoff for dedup |
| `MAX_ARTICLES_PER_SOURCE` | `100` | Upper bound per source per run |
| `FETCH_INTERVAL_MINUTES` | `30` | How often Notebook 4 polls (automation) |
| `MODEL_NAME` | varies | HuggingFace model ID for summarisation |

---

## Project Structure

```
ausflash/
├── 1_scrape_news_apify.ipynb    # Scraper v2
├── 2_summarise_csv.ipynb        # Summariser v2
├── 3_model_evaluation.ipynb     # Model benchmarking
├── 4_automation_apify.ipynb     # Automation v2
└── README.md
```

Generated at runtime (git-ignored):

```
smart_news_raw.csv
smart_news_summarised.csv
smart_news_live.csv
model_comparison.csv
```

---

## Roadmap

- [ ] Australian sources — ABC News AU, SBS, Sydney Morning Herald via RSS
- [ ] Web app — InShorts-style card swipe UI using GNews API
- [ ] Claude API summarisation — replace BART with Claude for higher quality 60-word summaries
- [ ] Docker container — one-command deployment for the automation pipeline
- [ ] GitHub Actions — scheduled scrape runs without a local machine

---

*Built for Australia. Inspired by InShorts.*
