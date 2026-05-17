"""
AusFlash — Daily Pipeline
Runs via GitHub Actions every day at 6 AM AEST.

Steps:
  1. Scrape articles from Apify
  2. Content filter (bad URLs, promo pages, no description)
  3. 48-hour date filter
  4. Exact title deduplication
  5. TF-IDF similarity deduplication
  6. Section classification
  7. Quick 60-word summary (no ML model — uses description truncation for speed)
  8. Upsert to Supabase (skips URLs already in DB)

Environment variables required (set as GitHub Actions secrets):
  APIFY_API_TOKEN   — from apify.com
  SUPABASE_URL      — from supabase.com project settings
  SUPABASE_KEY      — service role key (not anon key) from supabase.com
"""

import os
import sys
from datetime import datetime, timezone
from dateutil import parser as dateparser
from apify_client import ApifyClient
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from supabase import create_client

# ═══════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════
APIFY_API_TOKEN     = os.environ['APIFY_API_TOKEN']
SUPABASE_URL        = os.environ['SUPABASE_URL']
SUPABASE_KEY        = os.environ['SUPABASE_KEY']

ACTOR_ID            = 'complex_intricate_networks/news-article-scraper-100-global-sources-api'
MAX_AGE_HOURS       = 48
SIMILARITY_THRESHOLD = 0.70
MAX_ARTICLES        = 100

SOURCES = [
    'BBC World News',
    'Al Jazeera',
    'CNBC',
    'The New York Times',
    'TechCrunch',
    'Wired',
    'Variety',
    'The Guardian World News',
    'Business Insider',
    'Mashable',
    'Rolling Stone',
    'Vox',
    'TIME',
    'Ars Technica',
    'CNET News',
    'CBS News',
    'CoinDesk',
]

# ═══════════════════════════════════════════════════════
# SECTION CLASSIFIER
# ═══════════════════════════════════════════════════════
SECTION_KEYWORDS = {
    'Tech': [
        'ai', 'artificial intelligence', 'machine learning', 'software', 'app',
        'startup', 'google', 'apple', 'microsoft', 'meta', 'openai', 'nvidia',
        'chip', 'cybersecurity', 'hack', 'data breach', 'electric vehicle', 'ev',
        'tesla', 'smartphone', 'iphone', 'android', 'tech', 'technology',
        'developer', 'chatgpt', 'llm', 'drone', '5g', 'quantum', 'computer',
    ],
    'Politics': [
        'election', 'president', 'prime minister', 'parliament', 'congress',
        'senate', 'government', 'policy', 'democrat', 'republican', 'labour',
        'trump', 'biden', 'vote', 'ballot', 'legislation', 'minister',
        'cabinet', 'diplomat', 'sanctions', 'nato', 'united nations',
        'political', 'politician', 'campaign', 'opposition', 'albanese',
    ],
    'Business': [
        'stock', 'market', 'shares', 'economy', 'inflation', 'interest rate',
        'gdp', 'recession', 'investment', 'revenue', 'profit', 'earnings',
        'merger', 'bankruptcy', 'layoff', 'unemployment', 'trade', 'tariff',
        'finance', 'bank', 'crypto', 'bitcoin', 'wall street', 'asx', 'nasdaq',
    ],
    'Crime': [
        'murder', 'killed', 'arrested', 'charged', 'sentenced', 'prison',
        'jail', 'court', 'trial', 'verdict', 'police', 'shooting', 'stabbing',
        'robbery', 'fraud', 'scam', 'trafficking', 'terrorist', 'bomb',
        'hostage', 'kidnap', 'homicide', 'assault', 'corruption',
    ],
    'Science': [
        'research', 'study', 'scientists', 'discovery', 'space', 'nasa',
        'climate change', 'environment', 'species', 'gene', 'dna', 'vaccine',
        'virus', 'bacteria', 'cancer', 'pandemic', 'outbreak', 'disease',
        'astronomy', 'planet', 'telescope', 'reef', 'earthquake', 'volcano',
    ],
    'Sport': [
        'match', 'tournament', 'championship', 'league', 'cup', 'final',
        'score', 'goal', 'player', 'coach', 'transfer', 'football', 'soccer',
        'rugby', 'cricket', 'tennis', 'golf', 'basketball', 'nba', 'nfl',
        'nrl', 'afl', 'f1', 'formula 1', 'olympics', 'athlete', 'motogp',
    ],
    'Entertainment': [
        'movie', 'film', 'box office', 'oscar', 'bafta', 'emmy', 'grammy',
        'celebrity', 'actor', 'actress', 'album', 'concert', 'streaming',
        'netflix', 'disney', 'hbo', 'tv show', 'series', 'award',
        'singer', 'band', 'music', 'pop', 'hip hop', 'viral', 'tiktok',
    ],
    'Lifestyle': [
        'food', 'recipe', 'restaurant', 'travel', 'holiday', 'vacation',
        'wellness', 'mental health', 'fitness', 'workout', 'diet', 'parenting',
        'relationship', 'dating', 'wedding', 'home', 'fashion', 'beauty',
        'skincare', 'shopping', 'review', 'how to', 'tips', 'advice',
    ],
    'World': [
        'war', 'conflict', 'military', 'troops', 'attack', 'strike', 'missile',
        'ceasefire', 'humanitarian', 'refugee', 'ukraine', 'russia', 'israel',
        'gaza', 'iran', 'china', 'north korea', 'middle east', 'africa',
        'europe', 'asia', 'flood', 'disaster', 'protest', 'coup',
    ],
}
SECTION_PRIORITY = [
    'Crime', 'Tech', 'Politics', 'Business', 'Science',
    'Sport', 'Entertainment', 'Lifestyle', 'World',
]

def classify_section(title, description):
    text = (title + ' ' + description).lower()
    for section in SECTION_PRIORITY:
        if any(kw in text for kw in SECTION_KEYWORDS[section]):
            return section
    return 'World'


# ═══════════════════════════════════════════════════════
# FILTERS
# ═══════════════════════════════════════════════════════
BAD_URL_KEYWORDS = ['/video/', '/live-news/', '/category/', '/index',
                    '/watch', '/gallery/', '/podcast/', '/audio/', '/live/']
PROMO_KEYWORDS   = ['promo code', 'coupon', '% off', 'discount', 'gift guide']

def is_valid(item):
    url   = (item.get('url') or '').lower()
    title = (item.get('title') or '').lower().strip()
    desc  = (item.get('description') or '')
    if any(kw in url   for kw in BAD_URL_KEYWORDS): return False
    if any(kw in title for kw in PROMO_KEYWORDS):   return False
    if len(desc) < 20:                               return False
    return True


# ═══════════════════════════════════════════════════════
# DATE UTILITIES
# ═══════════════════════════════════════════════════════
def parse_dt(raw):
    if not raw or not isinstance(raw, str): return None
    try:
        dt = dateparser.parse(raw)
        return dt.replace(tzinfo=timezone.utc) if dt and not dt.tzinfo else dt
    except Exception:
        return None

def age_hours(dt):
    if dt is None: return 9999
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


# ═══════════════════════════════════════════════════════
# SIMILARITY DEDUP
# ═══════════════════════════════════════════════════════
def deduplicate_by_similarity(df, threshold=0.70):
    if len(df) < 2:
        return df
    texts      = (df['title'].fillna('') + ' ' + df['description'].fillna('')).tolist()
    vectorizer = TfidfVectorizer(stop_words='english', max_features=5000, ngram_range=(1, 2))
    tfidf      = vectorizer.fit_transform(texts)
    sim        = cosine_similarity(tfidf)
    to_drop    = set()
    for i in range(len(df)):
        if i in to_drop: continue
        for j in range(i + 1, len(df)):
            if j not in to_drop and sim[i, j] >= threshold:
                to_drop.add(j)
    result = df.drop(index=list(to_drop)).reset_index(drop=True)
    print(f'  Similarity dedup: {len(df)} → {len(result)} ({len(to_drop)} near-duplicates removed)')
    return result


# ═══════════════════════════════════════════════════════
# QUICK SUMMARY (60-word truncation — no ML model)
# Fast enough for GitHub Actions. Swap for BART if you
# run this locally with GPU.
# ═══════════════════════════════════════════════════════
def quick_summary(description):
    if not description or len(description.strip()) < 20:
        return 'Summary not available.'
    words = description.strip().split()
    if len(words) <= 60:
        return description.strip()
    return ' '.join(words[:60]) + '...'


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════
def main():
    print(f'\n{"="*60}')
    print(f'AusFlash Pipeline — {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}')
    print(f'{"="*60}')

    # ── Connect to Supabase ───────────────────────────────
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    print('Connected to Supabase.')

    # ── Fetch existing URLs to skip duplicates ────────────
    existing = sb.table('articles').select('url').execute()
    seen_urls = {row['url'] for row in existing.data}
    print(f'Existing articles in DB: {len(seen_urls)}')

    # ── Run Apify Actor ───────────────────────────────────
    print('\nCalling Apify Actor...')
    client = ApifyClient(APIFY_API_TOKEN)
    run    = client.actor(ACTOR_ID).call(run_input={
        'category':           'Top news',
        'countries':          ['Australia'],
        'sources':            SOURCES,
        'maxArticles':        MAX_ARTICLES,
        'keywordFilter':      '',
        'proxyConfiguration': {'useApifyProxy': True},
    })
    items = list(client.dataset(run['defaultDatasetId']).iterate_items())
    print(f'Apify returned {len(items)} raw articles.')

    # ── Content filter ────────────────────────────────────
    rows = []
    scrape_time = datetime.now().strftime('%H:%M:%S')
    for item in items:
        url = item.get('url', '')
        if not url or url in seen_urls: continue
        if not is_valid(item):          continue

        pub_dt  = parse_dt(item.get('published_at', ''))
        hrs_old = age_hours(pub_dt)
        if hrs_old > MAX_AGE_HOURS:     continue   # 48-hour filter

        title = (item.get('title') or '').strip()
        desc  = (item.get('description') or '').strip()
        rows.append({
            'website_name': item.get('source', '').strip(),
            'section':      '',
            'title':        title,
            'description':  desc,
            'ai_summary':   '',
            'url':          url,
            'published_at': pub_dt.isoformat() if pub_dt else None,
            'age_hours':    round(hrs_old, 1),
            'scrape_time':  scrape_time,
        })
        seen_urls.add(url)

    print(f'After content + date filter: {len(rows)} new articles')

    if not rows:
        print('No new articles. Exiting.')
        sys.exit(0)

    # ── Exact title dedup ─────────────────────────────────
    df     = pd.DataFrame(rows)
    before = len(df)
    df     = df.drop_duplicates(subset=['title']).reset_index(drop=True)
    print(f'Exact dedup: {before} → {len(df)}')

    # ── Similarity dedup ──────────────────────────────────
    df = deduplicate_by_similarity(df, threshold=SIMILARITY_THRESHOLD)

    # ── Section classification ────────────────────────────
    df['section']    = df.apply(lambda r: classify_section(r['title'], r['description']), axis=1)
    df['ai_summary'] = df['description'].apply(quick_summary)

    print(f'\nSection distribution:')
    print(df['section'].value_counts().to_string())

    # ── Upsert to Supabase ────────────────────────────────
    records = df.to_dict(orient='records')
    print(f'\nUpserting {len(records)} articles to Supabase...')

    # Batch in chunks of 100 to stay within Supabase limits
    chunk_size = 100
    inserted   = 0
    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        sb.table('articles').upsert(chunk, on_conflict='url').execute()
        inserted += len(chunk)
        print(f'  Upserted {inserted}/{len(records)}')

    print(f'\nDone. {len(records)} articles written to Supabase.')
    print(f'Total in DB: ~{len(seen_urls)}')


if __name__ == '__main__':
    main()
