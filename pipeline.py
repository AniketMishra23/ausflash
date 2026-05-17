"""
AusFlash — Daily Pipeline
Runs via GitHub Actions every day at 6 AM AEST.

Steps:
  1. Scrape articles from Apify
  2. Content filter (bad URLs, promo pages, no description)
  3. 48-hour date filter
  4. Exact title deduplication
  5. TF-IDF similarity deduplication
  6. Section classification (scoring-based — most keyword matches wins)
  7. Extractive summarisation via sumy (open-source, no model download)
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
import nltk
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)

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

# ── Australian RSS feeds (scraped directly via feedparser) ─
AUSTRALIAN_RSS_FEEDS = {
    'ABC News Australia':       'https://www.abc.net.au/news/feed/51120/rss.xml',
    'SBS News':                 'https://www.sbs.com.au/news/topic/latest/feed',
    'The Guardian Australia':   'https://www.theguardian.com/australia-news/rss',
    '9News Australia':          'https://www.9news.com.au/rss',
    'news.com.au':              'https://www.news.com.au/feed/',
    'Sky News Australia':       'https://feeds.skynews.com.au/feeds/rss/australia.xml',
    'The Sydney Morning Herald':'https://www.smh.com.au/rss/feed.xml',
    'Herald Sun':               'https://www.heraldsun.com.au/news/breaking-news/rss',
}

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
    # Specific phrases only — avoids false positives from single common words
    'Crime': [
        'murder', 'homicide', 'manslaughter', 'serial killer',
        'arrested for', 'charged with', 'pleaded guilty', 'not guilty',
        'prison sentence', 'jail sentence', 'life sentence', 'death sentence',
        'convicted of', 'criminal charges', 'criminal trial', 'criminal case',
        'shooting', 'stabbing', 'robbery', 'burglary', 'carjacking',
        'drug bust', 'drug trafficking', 'human trafficking',
        'terrorist attack', 'bomb threat', 'hostage', 'kidnapping',
        'domestic violence', 'sexual assault', 'rape',
        'fraud charges', 'money laundering', 'bribery charges',
        'gang violence', 'cartel', 'indicted', 'extradited',
        'wanted by police', 'fugitive', 'crime scene',
    ],
    'Tech': [
        'artificial intelligence', 'machine learning', 'software',
        'startup', 'google', 'apple', 'microsoft', 'meta', 'openai', 'nvidia',
        'chip', 'semiconductor', 'cybersecurity', 'data breach', 'hack',
        'electric vehicle', 'tesla', 'spacex', 'smartphone', 'iphone', 'android',
        'chatgpt', 'llm', 'generative ai', '5g', 'quantum computing',
        'tech company', 'silicon valley', 'app store', 'cloud computing',
        'robotics', 'autonomous vehicle', 'deepmind', 'anthropic',
    ],
    'Politics': [
        'election', 'president', 'prime minister', 'parliament', 'congress',
        'senate', 'government policy', 'democrat', 'republican', 'labour party',
        'trump', 'biden', 'vote', 'ballot', 'referendum', 'legislation',
        'cabinet minister', 'diplomat', 'sanctions', 'nato', 'united nations',
        'political party', 'politician', 'campaign', 'albanese', 'dutton',
        'white house', 'supreme court ruling', 'executive order',
    ],
    'Business': [
        'stock market', 'shares', 'economy', 'inflation', 'interest rate',
        'federal reserve', 'reserve bank', 'gdp', 'recession', 'investment',
        'quarterly earnings', 'revenue', 'profit', 'merger', 'acquisition',
        'ipo', 'bankruptcy', 'layoffs', 'unemployment rate', 'trade war',
        'tariff', 'wall street', 'asx', 'nasdaq', 'crypto', 'bitcoin',
        'hedge fund', 'venture capital', 'real estate market',
    ],
    'Science': [
        'scientists', 'researchers found', 'new study', 'discovery',
        'nasa', 'space mission', 'climate change', 'carbon emissions',
        'species', 'fossil', 'genome', 'dna', 'vaccine', 'clinical trial',
        'virus outbreak', 'bacteria', 'cancer treatment', 'pandemic',
        'astronomy', 'black hole', 'telescope', 'coral reef',
        'earthquake', 'volcanic eruption', 'ocean temperature',
    ],
    'Sport': [
        'match', 'tournament', 'championship', 'league', 'cup final',
        'score', 'goal', 'transfer fee', 'football', 'soccer', 'rugby',
        'cricket', 'tennis', 'golf', 'basketball', 'nba', 'nfl',
        'nrl', 'afl', 'formula 1', 'f1 race', 'olympics', 'athlete',
        'wimbledon', 'world cup', 'grand slam', 'motogp', 'ufc',
    ],
    'Entertainment': [
        'box office', 'oscar', 'bafta', 'emmy', 'grammy', 'cannes',
        'celebrity', 'actor', 'actress', 'album release', 'concert tour',
        'netflix', 'disney+', 'hbo', 'tv series', 'film review',
        'music video', 'pop star', 'hip hop', 'red carpet', 'movie trailer',
        'box office', 'streaming service', 'tiktok trend',
    ],
    'Lifestyle': [
        'recipe', 'restaurant review', 'travel guide', 'vacation',
        'mental health', 'fitness routine', 'workout', 'diet plan',
        'parenting', 'relationship advice', 'wedding', 'interior design',
        'fashion week', 'skincare', 'wellness', 'meditation',
    ],
    'World': [
        'war', 'conflict', 'military', 'troops', 'airstrike', 'missile',
        'ceasefire', 'humanitarian crisis', 'refugee', 'ukraine', 'russia',
        'israel', 'gaza', 'iran', 'north korea', 'middle east',
        'flood', 'natural disaster', 'protest', 'coup', 'revolution',
        'foreign minister', 'bilateral talks', 'un peacekeepers',
    ],
}

# Scoring-based classifier — section with most keyword matches wins.
# World is the fallback when nothing else matches.
def classify_section(title, description):
    text   = (title + ' ' + description).lower()
    scores = {
        section: sum(1 for kw in kws if kw in text)
        for section, kws in SECTION_KEYWORDS.items()
        if section != 'World'
    }
    best_score = max(scores.values(), default=0)
    if best_score == 0:
        return 'World'
    # Among sections tied for best score, pick by priority order
    priority = ['Crime', 'Tech', 'Politics', 'Business', 'Science',
                'Sport', 'Entertainment', 'Lifestyle']
    for section in priority:
        if scores.get(section, 0) == best_score:
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
# AUSTRALIAN RSS SCRAPER
# ═══════════════════════════════════════════════════════
def scrape_australian_rss(seen_urls, scrape_time):
    try:
        import feedparser
    except ImportError:
        print('feedparser not installed — skipping Australian RSS sources.')
        return []

    rows = []
    for source_name, feed_url in AUSTRALIAN_RSS_FEEDS.items():
        try:
            feed    = feedparser.parse(feed_url)
            entries = feed.entries
            print(f'  {source_name}: {len(entries)} entries')
            for entry in entries:
                url = entry.get('link', '')
                if not url or url in seen_urls:
                    continue

                title = (entry.get('title') or '').strip()
                desc  = (
                    entry.get('summary') or
                    entry.get('description') or
                    entry.get('content', [{}])[0].get('value', '')
                ).strip()

                # Strip HTML tags from description
                import re
                desc = re.sub(r'<[^>]+>', '', desc).strip()

                if not title or len(desc) < 20:
                    continue

                # Check for bad URLs and promo content
                url_lower = url.lower()
                if any(kw in url_lower for kw in BAD_URL_KEYWORDS):
                    continue
                if any(kw in title.lower() for kw in PROMO_KEYWORDS):
                    continue

                pub_dt  = parse_dt(entry.get('published') or entry.get('updated') or '')
                hrs_old = age_hours(pub_dt)
                if hrs_old > MAX_AGE_HOURS:
                    continue

                rows.append({
                    'website_name': source_name,
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

        except Exception as e:
            print(f'  {source_name}: failed — {e}')

    print(f'Australian RSS total: {len(rows)} new articles')
    return rows


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
# SUMMARISATION — sumy (open-source, no model download)
# Uses Luhn extractive algorithm to pick the most
# informative sentences from the description.
# Falls back to sentence-aware truncation if sumy fails.
# ═══════════════════════════════════════════════════════
try:
    from sumy.parsers.plaintext import PlaintextParser
    from sumy.nlp.tokenizers import Tokenizer
    from sumy.summarizers.luhn import LuhnSummarizer
    _sumy_ready = True
except ImportError:
    _sumy_ready = False

def summarise(title, description):
    text = (description or '').strip()
    if not text or len(text) < 30:
        return text or 'Summary not available.'

    # sumy extractive summarisation
    if _sumy_ready:
        try:
            combined = f'{title}. {text}'
            parser   = PlaintextParser.from_string(combined, Tokenizer('english'))
            summary  = LuhnSummarizer()(parser.document, sentences_count=2)
            result   = ' '.join(str(s) for s in summary).strip()
            if result:
                words = result.split()
                return ' '.join(words[:60]) + ('...' if len(words) > 60 else '')
        except Exception:
            pass

    # Fallback: sentence-aware truncation
    words = text.split()
    if len(words) <= 60:
        return text
    chunk = ' '.join(words[:60])
    for punct in ('. ', '! ', '? '):
        idx = chunk.rfind(punct)
        if idx > 20:
            return chunk[:idx + 1]
    return chunk + '...'


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

    print(f'Apify after filter: {len(rows)} new articles')

    # ── Australian RSS sources ────────────────────────────
    print('\nScraping Australian RSS feeds...')
    aus_rows = scrape_australian_rss(seen_urls, scrape_time)
    rows.extend(aus_rows)
    print(f'Combined total: {len(rows)} new articles')

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
    df['ai_summary'] = df.apply(lambda r: summarise(r['title'], r['description']), axis=1)

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
