# AusFlash

> **Global news. Australian speed.**

AusFlash is an InShorts-style news app for Australia — a fully automated, end-to-end pipeline that scrapes global and Australian news, deduplicates stories, classifies them into sections, and generates abstractive summaries using a fine-tuned BART model. The result is delivered through a mobile app where users swipe through one clean card per story.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│           GitHub Actions (6 AM AEST)         │
│                  pipeline.py                 │
│                                             │
│  Apify Actor          Australian RSS Feeds  │
│  (17 global sources)  (8 AU sources)        │
│         ↓                    ↓              │
│         └────────┬───────────┘              │
│                  ↓                          │
│         Content + Date Filter               │
│         (bad URLs, >48h old, no desc)       │
│                  ↓                          │
│         Exact Title Dedup                   │
│                  ↓                          │
│         TF-IDF Cosine Similarity Dedup      │
│                  ↓                          │
│         Section Classifier (9 sections)     │
│                  ↓                          │
│         BART Abstractive Summariser         │
│         (sshleifer/distilbart-cnn-12-6)     │
│                  ↓                          │
│              Supabase                       │
└─────────────────────────────────────────────┘
                   ↓
        FastAPI on Render (api/index.py)
                   ↓
        Expo React Native App (iOS + Android)
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| Scraping (global) | [Apify](https://apify.com) — `complex_intricate_networks/news-article-scraper-100-global-sources-api` |
| Scraping (Australia) | `feedparser` — 8 AU RSS feeds |
| Deduplication | `scikit-learn` TF-IDF cosine similarity |
| Summarisation | `sshleifer/distilbart-cnn-12-6` via HuggingFace Transformers |
| Database | [Supabase](https://supabase.com) (PostgreSQL) |
| API | FastAPI deployed on [Render](https://render.com) |
| Mobile app | Expo SDK 54 (React Native) |
| Automation | GitHub Actions — cron `0 20 * * *` (6 AM AEST) |

---

## News Sources

### Global (via Apify)
BBC World News, Al Jazeera, CNBC, The New York Times, TechCrunch, Wired, Variety, The Guardian World News, Business Insider, Mashable, Rolling Stone, Vox, TIME, Ars Technica, CNET News, CBS News, CoinDesk

### Australian (via RSS)
ABC News Australia, SBS News, The Guardian Australia, 9News Australia, The Sydney Morning Herald, Australian Financial Review, Crikey, The New Daily

---

## Pipeline Steps

### 1. Scrape
- **Apify actor** fetches up to 100 articles from 17 global sources, biased toward Australia-relevant stories
- **feedparser** pulls all 8 Australian RSS feeds, spoofing a Chrome user-agent to bypass bot-blocking
- Already-stored URLs (fetched from Supabase at startup) are skipped to avoid reprocessing

### 2. Filter
- Drop articles with bad URL patterns (`/video/`, `/live-news/`, `/gallery/`, etc.)
- Drop sponsored/affiliate content (promo code, coupon, % off, etc.)
- Drop articles with descriptions shorter than 20 characters
- Drop articles older than 48 hours

### 3. Deduplicate
- **Exact title dedup** — drop articles with identical titles
- **Similarity dedup** — TF-IDF on `title + description`, bigrams, cosine similarity ≥ 0.70 → drop the later article

### 4. Classify
Scoring-based keyword match on `title + description`. Each section has a weighted keyword list; the section with the most matches wins. On a tie, more specific sections (Crime, Tech) beat general ones (World).

| Priority | Section | Example keywords |
|----------|---------|-----------------|
| 1 | Crime | arrested, murder, charged, trial, shooting, fraud |
| 2 | Tech | ai, google, apple, hack, chip, chatgpt, openai |
| 3 | Politics | election, parliament, trump, albanese, vote, nato |
| 4 | Business | stock, inflation, rba, layoff, crypto, bitcoin |
| 5 | Science | nasa, climate, vaccine, csiro, reef, outbreak |
| 6 | Sport | nrl, afl, cricket, f1, nba, grand final, ashes |
| 7 | Entertainment | netflix, oscar, album, concert, celebrity |
| 8 | Lifestyle | recipe, travel, wellness, fitness, parenting |
| 9 | World | war, ceasefire, refugee, ukraine, iran, disaster |

### 5. Summarise
Uses `sshleifer/distilbart-cnn-12-6` — a DistilBART model fine-tuned on CNN/DailyMail news. This model **writes new sentences** rather than copying from the source, so summaries are genuinely informative and don't just repeat the headline.

Output format stored in `ai_summary`:
```
Bold lead sentence (what happened)
\n
Supporting body (context, ~40 words)
```

The mobile app splits on `\n` — the lead is rendered bold, the body in grey.

Falls back to extractive sentence-split if the model fails to load.

### 6. Upsert
Batched upserts to Supabase in chunks of 100. `on_conflict='url'` — existing articles are updated with the latest summary if pipeline logic has changed.

---

## API Endpoints

Deployed on Render: `https://ausflash.onrender.com`

| Method | Endpoint | Description |
|--------|---------|-------------|
| GET | `/` | Health check |
| GET | `/feed` | Latest articles (all sections) |
| GET | `/feed?section=Tech` | Filter by section |
| GET | `/feed?limit=50&offset=50` | Paginate |
| GET | `/sections` | Article count per section |
| GET | `/article/{id}` | Single article by UUID |

---

## Mobile App

Built with Expo SDK 54 + expo-router.

- **InShorts-style vertical swipe** — one full-screen card per article, `FlatList` with `pagingEnabled`
- **Section tabs** — All, Tech, Politics, Business, Crime, Science, Sport, Entertainment, Lifestyle, World
- **Pull to refresh** — bumps the feed with latest articles
- **Client-side dedup** — normalises first 8 words of each title to catch near-duplicates that got through
- **Ad placeholders** — every 5 cards (AdMob-ready)
- **Colour-coded sections** — each section has a unique accent colour applied to the badge, divider, and button

### Running locally
```bash
cd ausflash-app
npm install
npx expo start
```

Press `a` for Android emulator, `i` for iOS simulator, or scan the QR code with Expo Go.

---

## GitHub Actions Workflow

The pipeline runs automatically at **6:00 AM AEST** every day.

```yaml
cron: '0 20 * * *'   # 8 PM UTC = 6 AM AEST
timeout-minutes: 45
```

**Caches:**
- `pip` — keyed to `requirements.txt`
- HuggingFace model weights — static key `hf-distilbart-cnn-12-6` (~900 MB, downloads once)
- PyTorch CPU build — installed separately to avoid pulling the 2.5 GB CUDA build

**Secrets required:**
- `APIFY_API_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_KEY` (service role key)

Trigger a manual run anytime from the **Actions** tab → **AusFlash Daily Pipeline** → **Run workflow**.

---

## Project Structure

```
ausflash/
├── pipeline.py                   # Main daily pipeline
├── reprocess.py                  # One-time re-summarise script (run locally, then delete)
├── requirements.txt              # Python dependencies
├── schema.sql                    # Supabase table definition
│
├── api/
│   └── index.py                  # FastAPI backend (deployed on Render)
│
├── ausflash-app/                 # Expo React Native app
│   ├── app/
│   │   └── (tabs)/index.tsx      # Main feed screen
│   ├── components/
│   │   ├── NewsCard.tsx          # Full-screen article card
│   │   └── SectionTabs.tsx       # Horizontal section filter
│   ├── hooks/
│   │   └── useFeed.ts            # API fetch hook
│   └── constants/
│       └── api.ts                # API URL + section colours
│
└── .github/
    └── workflows/
        └── daily_pipeline.yml    # GitHub Actions cron job
```

---

## Roadmap

- [x] Australian RSS sources (ABC, SBS, Guardian AU, 9News, SMH, AFR, Crikey, The New Daily)
- [x] InShorts-style mobile app (Expo, vertical swipe)
- [x] Supabase + FastAPI backend
- [x] GitHub Actions automation
- [x] BART abstractive summarisation
- [ ] AdMob integration — replace ad placeholders with real banners
- [ ] Qonversion paywall — subscription to remove ads
- [ ] Google Play + App Store publishing via `eas build`
- [ ] Render cold-start fix — upgrade from free tier or add keep-alive ping

---

*Built for Australia. Inspired by InShorts.*
