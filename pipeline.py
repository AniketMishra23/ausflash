"""
AusFlash — Daily Pipeline
Runs automatically via GitHub Actions every day at 6 AM AEST.

Steps:
  1. Fetch existing URLs from Supabase (to skip already-stored articles)
  2. Scrape global articles via Apify actor
  3. Scrape Australian articles via feedparser RSS
  4. Content filter  — drop bad URLs, promo pages, short descriptions
  5. 48-hour date filter — drop articles older than MAX_AGE_HOURS
  6. Exact title dedup — drop identical titles across sources
  7. TF-IDF cosine similarity dedup — drop near-duplicate stories (≥ 0.70)
  8. Section classification — scoring-based keyword match (most hits wins)
  9. Abstractive summarisation — sshleifer/distilbart-cnn-12-6 (falls back to extractive on error)
  10. Upsert to Supabase — on_conflict='url' skips any URL already stored

Required environment variables (set as GitHub Actions secrets):
  APIFY_API_TOKEN   — from apify.com
  SUPABASE_URL      — Supabase project URL (Settings → API)
  SUPABASE_KEY      — service role key, NOT the anon key (has write access)
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
MAX_AGE_HOURS        = 48    # articles older than this are discarded
SIMILARITY_THRESHOLD = 0.70  # cosine similarity above this → near-duplicate, keep first
MAX_ARTICLES         = 100   # max articles to request from the Apify actor per run

# ── Australian RSS feeds (scraped directly via feedparser) ─
# news.com.au, Sky News AU, Herald Sun returned 0 entries — likely blocking
# feedparser's default user-agent or their feed URLs changed.
# Replaced with The Age, Brisbane Times, and WA Today (same Nine/Fairfax
# network as SMH — reliable open RSS feeds).
AUSTRALIAN_RSS_FEEDS = {
    'ABC News Australia':       'https://www.abc.net.au/news/feed/51120/rss.xml',
    'SBS News':                 'https://www.sbs.com.au/news/topic/latest/feed',
    'The Guardian Australia':   'https://www.theguardian.com/australia-news/rss',
    '9News Australia':          'https://www.9news.com.au/rss',
    'The Sydney Morning Herald': 'https://www.smh.com.au/rss/feed.xml',
    # Replacing The Age / Brisbane Times / WA Today — same Fairfax network as SMH,
    # identical articles cause ~40 wasted dedup slots each run.
    'Australian Financial Review': 'https://www.afr.com/rss',
    'Crikey':                    'https://www.crikey.com.au/feed/',
    'The New Daily':             'https://thenewdaily.com.au/feed/',
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
    # Specific phrases only — avoids false positives from single common words.
    # AU-specific terms are marked with # AU so they're easy to maintain.
    'Crime': [
        # Global crime
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
        # AU
        'nsw police', 'victoria police', 'queensland police', 'afp',
        'australian federal police', 'court heard', 'magistrate',
        'supreme court', 'inquest', 'coronial', 'bail refused',
    ],
    'Tech': [
        # Global tech
        'artificial intelligence', 'machine learning', 'software',
        'startup', 'google', 'apple', 'microsoft', 'meta', 'openai', 'nvidia',
        'chip', 'semiconductor', 'cybersecurity', 'data breach', 'hack',
        'electric vehicle', 'tesla', 'spacex', 'smartphone', 'iphone', 'android',
        'chatgpt', 'llm', 'generative ai', '5g', 'quantum computing',
        'tech company', 'silicon valley', 'app store', 'cloud computing',
        'robotics', 'autonomous vehicle', 'deepmind', 'anthropic',
        # AU
        'asx tech', 'canva', 'atlassian', 'afterpay', 'fintech',
        'nbn', 'myhealth', 'digital id',
    ],
    'Politics': [
        # Global politics
        'election', 'president', 'prime minister', 'parliament', 'congress',
        'senate', 'government policy', 'democrat', 'republican', 'labour party',
        'trump', 'biden', 'vote', 'ballot', 'referendum', 'legislation',
        'cabinet minister', 'diplomat', 'sanctions', 'nato', 'united nations',
        'political party', 'politician', 'campaign',
        'white house', 'supreme court ruling', 'executive order',
        # AU — parties, leaders, institutions
        'albanese', 'dutton', 'greens party', 'anthony albanese',
        'peter dutton', 'liberal party', 'labor party', 'the nationals',
        'federal budget', 'federal government', 'state government',
        'premier', 'treasurer', 'shadow minister', 'crossbench',
        'house of representatives', 'australian senate', 'aec',
        'voice to parliament', 'aukus', 'asio', 'home affairs',
    ],
    'Business': [
        # Global business
        'stock market', 'shares', 'economy', 'inflation', 'interest rate',
        'federal reserve', 'gdp', 'recession', 'investment',
        'quarterly earnings', 'revenue', 'profit', 'merger', 'acquisition',
        'ipo', 'bankruptcy', 'layoffs', 'unemployment rate', 'trade war',
        'tariff', 'wall street', 'nasdaq', 'crypto', 'bitcoin',
        'hedge fund', 'venture capital', 'real estate market',
        # AU
        'reserve bank', 'rba', 'asx', 'asx 200', 'australian dollar', 'aud',
        'cost of living', 'housing affordability', 'mortgage rate',
        'superannuation', 'cba', 'anz', 'westpac', 'nab',
        'woolworths', 'coles', 'qantas', 'bhp', 'rio tinto',
    ],
    'Science': [
        # Global science
        'scientists', 'researchers found', 'new study', 'discovery',
        'nasa', 'space mission', 'climate change', 'carbon emissions',
        'species', 'fossil', 'genome', 'dna', 'vaccine', 'clinical trial',
        'virus outbreak', 'bacteria', 'cancer treatment', 'pandemic',
        'astronomy', 'black hole', 'telescope',
        'earthquake', 'volcanic eruption', 'ocean temperature',
        # AU
        'great barrier reef', 'coral bleaching', 'csiro',
        'australian museum', 'bushfire research', 'murray-darling',
        'marine protected', 'endangered species australia',
    ],
    'Sport': [
        # Global sport
        'tournament', 'championship', 'cup final',
        'transfer fee', 'football', 'soccer', 'rugby',
        'tennis', 'golf', 'basketball', 'nba', 'nfl',
        'formula 1', 'f1 race', 'olympics', 'athlete',
        'wimbledon', 'grand slam', 'motogp', 'ufc',
        # AU — codes, leagues, events
        'nrl', 'afl', 'cricket australia', 'a-league', 'super rugby',
        'state of origin', 'grand final', 'test match', 'ashes',
        'australian open', 'commonwealth games', 'socceroos', 'wallabies',
        'kangaroos', 'matildas', 'boomers', 'opals',
        'premiership', 'finals series', 'wooden spoon',
        # Common sport reporting phrases
        'match', 'league', 'score', 'goal',
    ],
    'Entertainment': [
        # Global entertainment
        'box office', 'oscar', 'bafta', 'emmy', 'grammy', 'cannes',
        'celebrity', 'actor', 'actress', 'album release', 'concert tour',
        'netflix', 'disney+', 'hbo', 'tv series', 'film review',
        'music video', 'pop star', 'hip hop', 'red carpet', 'movie trailer',
        'streaming service', 'tiktok trend',
        # AU
        'aria awards', 'aacta', 'australian idol', 'masterchef australia',
        'the block', 'neighbours', 'home and away', 'australian film',
    ],
    'Lifestyle': [
        # Global lifestyle
        'recipe', 'restaurant review', 'travel guide', 'vacation',
        'mental health', 'fitness routine', 'workout', 'diet plan',
        'parenting', 'relationship advice', 'wedding', 'interior design',
        'fashion week', 'skincare', 'wellness', 'meditation',
        # AU
        'public holiday', 'school holidays', 'australian travel',
        'cost of living tips', 'renters', 'first home buyer',
    ],
    'World': [
        'war', 'conflict', 'military', 'troops', 'airstrike', 'missile',
        'ceasefire', 'humanitarian crisis', 'refugee', 'ukraine', 'russia',
        'israel', 'gaza', 'iran', 'north korea', 'middle east',
        'flood', 'natural disaster', 'protest', 'coup', 'revolution',
        'foreign minister', 'bilateral talks', 'un peacekeepers',
    ],
}

# Scoring-based classifier:
#   - Count how many keywords from each section appear in the article text.
#   - The section with the most matches wins.
#   - On a tie, the section that appears earlier in PRIORITY wins.
#   - If nothing matches, fall back to 'World' (catch-all for international news).
def classify_section(title, description):
    text = (title + ' ' + description).lower()

    # Score every section except World (World is the fallback, not a competitor)
    scores = {
        section: sum(1 for kw in kws if kw in text)
        for section, kws in SECTION_KEYWORDS.items()
        if section != 'World'
    }
    best_score = max(scores.values(), default=0)

    if best_score == 0:
        return 'World'  # no keyword matched → treat as international news

    # Tie-break: Crime > Tech > Politics > ... (more specific sections rank higher)
    priority = ['Crime', 'Tech', 'Politics', 'Business', 'Science',
                'Sport', 'Entertainment', 'Lifestyle']
    for section in priority:
        if scores.get(section, 0) == best_score:
            return section
    return 'World'


# ═══════════════════════════════════════════════════════
# FILTERS
# ═══════════════════════════════════════════════════════
# URL patterns that indicate non-article pages (video hubs, live blogs, category indexes)
BAD_URL_KEYWORDS = ['/video/', '/live-news/', '/category/', '/index',
                    '/watch', '/gallery/', '/podcast/', '/audio/', '/live/']
# Title phrases that indicate sponsored / affiliate content
PROMO_KEYWORDS   = ['promo code', 'coupon', '% off', 'discount', 'gift guide']

def is_valid(item):
    url   = (item.get('url') or '').lower()
    title = (item.get('title') or '').lower().strip()
    desc  = (item.get('description') or '')
    if any(kw in url   for kw in BAD_URL_KEYWORDS): return False
    if any(kw in title for kw in PROMO_KEYWORDS):   return False
    if len(desc) < 20: return False  # no meaningful content to summarise
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

    # Spoof a browser user-agent — some AU news sites block Python's default UA
    feedparser.USER_AGENT = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    )

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
    """
    Remove near-duplicate articles using TF-IDF cosine similarity.

    Two articles are considered duplicates when their combined title+description
    vectors have cosine similarity >= threshold.  We keep the first article
    (whichever appeared earlier in the list, usually from a higher-priority source)
    and drop the later one.
    """
    if len(df) < 2:
        return df

    # Combine title + description so both headline and body influence similarity
    texts = (df['title'].fillna('') + ' ' + df['description'].fillna('')).tolist()

    # Bigrams (ngram_range=(1,2)) capture phrases like "interest rate" better than unigrams alone
    vectorizer = TfidfVectorizer(stop_words='english', max_features=5000, ngram_range=(1, 2))
    tfidf      = vectorizer.fit_transform(texts)
    sim        = cosine_similarity(tfidf)  # n×n matrix

    to_drop = set()
    for i in range(len(df)):
        if i in to_drop: continue
        for j in range(i + 1, len(df)):
            # Mark j for removal if it's too similar to i (which we're keeping)
            if j not in to_drop and sim[i, j] >= threshold:
                to_drop.add(j)

    result = df.drop(index=list(to_drop)).reset_index(drop=True)
    print(f'  Similarity dedup: {len(df)} → {len(result)} ({len(to_drop)} near-duplicates removed)')
    return result


# ═══════════════════════════════════════════════════════
# SUMMARISATION — sshleifer/distilbart-cnn-12-6
#
# Abstractive model fine-tuned on CNN/DailyMail news.
# Generates genuinely new sentences — does not echo the
# headline the way extractive methods do.
#
# Output format (stored in ai_summary):
#   "lead sentence\nbody sentence(s)"
#   The frontend splits on \n: lead is bold, body is grey.
#
# Falls back to extractive sentence-split if the model
# fails to load or raises an error at inference time.
# ═══════════════════════════════════════════════════════
try:
    from transformers import pipeline as hf_pipeline
    _summarizer = hf_pipeline(
        'summarization',
        model='sshleifer/distilbart-cnn-12-6',
        device=-1,        # CPU — no GPU in GitHub Actions
    )
    _hf_ready = True
    print('BART summarizer loaded.')
except Exception as _e:
    _hf_ready = False
    print(f'BART not available ({_e}) — using extractive fallback.')

def _truncate(text, max_words=65):
    """Sentence-aware truncation at max_words."""
    words = text.split()
    if len(words) <= max_words:
        return text
    chunk = ' '.join(words[:max_words])
    for punct in ('. ', '! ', '? '):
        idx = chunk.rfind(punct)
        if idx > 20:
            return chunk[:idx + 1]
    return chunk + '...'

def _word_overlap(sentence, title):
    """
    Fraction of the sentence's words that also appear in the title (0–1).
    Used to detect sentences that are just a headline rewrite.
    """
    s_words = set(sentence.lower().split())
    t_words = set(title.lower().split())
    if not s_words:
        return 0.0
    return len(s_words & t_words) / len(s_words)

def _clean(s):
    """Strip trailing stray punctuation/spaces left by BART."""
    return s.strip().rstrip(' .')

def summarise(title, description):
    import re
    text = (description or '').strip()
    if not text:
        return title or 'Summary not available.'

    # ── Abstractive path (BART) ────────────────────────────
    if _hf_ready:
        try:
            combined  = f'{title}. {text}'
            input_len = len(combined.split())
            max_len   = min(90, max(30, input_len // 2))
            # Raised floor to 30 so short articles still get a decent summary
            min_len   = min(55, max(30, max_len - 10))
            result    = _summarizer(
                combined,
                max_length=max_len,
                min_length=min_len,
                do_sample=False,
                truncation=True,
            )
            summary = result[0]['summary_text'].strip()
            if summary:
                parts = [_clean(s) for s in re.split(r'(?<=[.!?])\s+', summary)
                         if len(s.strip()) > 5]
                if parts:
                    lead = parts[0]
                    rest = parts[1:]

                    # If BART's lead just echoes the title, skip it and
                    # promote the next sentence (or fall back to title as lead).
                    if _word_overlap(lead, title) > 0.55:
                        if rest:
                            lead = rest[0]
                            rest = rest[1:]
                        else:
                            # Whole summary is a title echo — use title as lead
                            return f'{title}\n{_clean(summary)}'

                    body = ' '.join(rest)
                    return f'{lead}\n{body}' if body else f'{title}\n{lead}'
        except Exception as _e:
            print(f'  BART inference error: {_e} — using extractive fallback.')

    # ── Extractive fallback ────────────────────────────────
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text)
                 if len(s.strip()) > 10]
    if not sentences:
        return f'{title}\n{_truncate(text, max_words=40)}'

    # Skip sentences that are headline rewrites; use title as lead instead.
    lead, rest = None, []
    for i, s in enumerate(sentences):
        if _word_overlap(s, title) <= 0.55:
            lead = s
            rest = sentences[i + 1:]
            break
    if lead is None:
        lead = title
        rest = sentences

    if rest:
        return f'{lead}\n{_truncate(" ".join(rest), max_words=40)}'
    return f'{title}\n{_truncate(lead, max_words=40)}'


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

    # ── Fetch existing URLs ───────────────────────────────
    # Pre-loading all URLs lets us skip Supabase round-trips for each article.
    # Also passed into scrape_australian_rss() so RSS sources don't re-add
    # articles that Apify already returned.
    existing = sb.table('articles').select('url').execute()
    seen_urls = {row['url'] for row in existing.data}
    print(f'Existing articles in DB: {len(seen_urls)}')

    # ── Apify scrape (optional — skipped if credits are exhausted) ──
    # The actor fetches top-news articles from the sources listed in SOURCES.
    # 'countries': ['Australia'] biases results toward Australian-relevant stories.
    # Wrapped in try/except so the pipeline continues with RSS-only on failure.
    rows = []
    scrape_time = datetime.now().strftime('%H:%M:%S')
    items = []
    print('\nCalling Apify Actor...')
    try:
        client = ApifyClient(APIFY_API_TOKEN)
        run    = client.actor(ACTOR_ID).call(run_input={
            'category':           'Top news',
            'countries':          ['Australia'],  # geographic bias
            'sources':            SOURCES,
            'maxArticles':        MAX_ARTICLES,
            'keywordFilter':      '',             # no keyword restriction — keep everything
            'proxyConfiguration': {'useApifyProxy': True},
        })
        # iterate_items() streams results without loading the full dataset into memory
        items = list(client.dataset(run['defaultDatasetId']).iterate_items())
        print(f'Apify returned {len(items)} raw articles.')
    except Exception as e:
        print(f'Apify skipped — {e}')
        print('Continuing with Australian RSS feeds only.')

    # ── Content filter ────────────────────────────────────
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

    # Batch in chunks of 100 — Supabase rejects very large single payloads.
    # on_conflict='url' means: if the URL already exists, update the row
    # (re-classifies section/summary if pipeline logic has improved).
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
