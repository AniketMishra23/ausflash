"""
AusFlash — One-Time Re-process Script
Re-classifies and re-summarises all existing articles in Supabase
using the improved scorer-based classifier and sumy summariser.

Run once locally:
  pip install supabase sumy nltk scikit-learn
  set SUPABASE_URL=your_url
  set SUPABASE_KEY=your_service_role_key
  python reprocess.py

Safe to delete after running.
"""

import os
import nltk
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)

from supabase import create_client

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_KEY']

# ── Section classifier (same as pipeline.py) ─────────────
SECTION_KEYWORDS = {
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
        'streaming service', 'tiktok trend',
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
PRIORITY = ['Crime', 'Tech', 'Politics', 'Business', 'Science',
            'Sport', 'Entertainment', 'Lifestyle']

def classify_section(title, description):
    text   = (title + ' ' + description).lower()
    scores = {
        s: sum(1 for kw in kws if kw in text)
        for s, kws in SECTION_KEYWORDS.items()
        if s != 'World'
    }
    best = max(scores.values(), default=0)
    if best == 0:
        return 'World'
    for s in PRIORITY:
        if scores.get(s, 0) == best:
            return s
    return 'World'

# ── Summariser (sumy) ─────────────────────────────────────
try:
    from sumy.parsers.plaintext import PlaintextParser
    from sumy.nlp.tokenizers import Tokenizer
    from sumy.summarizers.luhn import LuhnSummarizer
    _sumy_ready = True
    print('sumy loaded.')
except ImportError:
    _sumy_ready = False
    print('sumy not installed — run: pip install sumy nltk')

def summarise(title, description):
    text = (description or '').strip()
    if not text or len(text) < 30:
        return text or 'Summary not available.'
    if _sumy_ready:
        try:
            parser  = PlaintextParser.from_string(f'{title}. {text}', Tokenizer('english'))
            result  = ' '.join(str(s) for s in LuhnSummarizer()(parser.document, 2)).strip()
            if result:
                words = result.split()
                return ' '.join(words[:60]) + ('...' if len(words) > 60 else '')
        except Exception:
            pass
    words = text.split()
    if len(words) <= 60:
        return text
    chunk = ' '.join(words[:60])
    for punct in ('. ', '! ', '? '):
        idx = chunk.rfind(punct)
        if idx > 20:
            return chunk[:idx + 1]
    return chunk + '...'

# ── Main ──────────────────────────────────────────────────
def main():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    print('Fetching all articles from Supabase...')
    result   = sb.table('articles').select('id, title, description, section, ai_summary').execute()
    articles = result.data
    print(f'Found {len(articles)} articles to reprocess.\n')

    updated = 0
    for i, article in enumerate(articles):
        title = article.get('title', '') or ''
        desc  = article.get('description', '') or ''

        new_section = classify_section(title, desc)
        new_summary = summarise(title, desc)

        sb.table('articles').update({
            'section':    new_section,
            'ai_summary': new_summary,
        }).eq('id', article['id']).execute()

        updated += 1
        print(f'[{updated}/{len(articles)}] [{new_section}] {title[:60]}')

    print(f'\nDone. {updated} articles reprocessed.')

if __name__ == '__main__':
    main()
