"""
AusFlash — One-Time Re-process Script
Re-summarises all existing articles in Supabase using the current
pipeline logic (50-word minimum, headline-overlap filter, sumy Luhn).

Run once locally after any summarisation logic change:
  pip install supabase sumy nltk
  set SUPABASE_URL=your_url
  set SUPABASE_KEY=your_service_role_key
  python reprocess.py

Safe to delete after running.
"""

import os
import re
import nltk
nltk.download('punkt',     quiet=True)
nltk.download('punkt_tab', quiet=True)

from supabase import create_client

SUPABASE_URL = 'https://numxnyibpcayiikuotzf.supabase.co'
SUPABASE_KEY = 'sb_publishable_47AlYmJdgJQaGPBJbGL-3Q_9sd7Qcli'

# ── Summarisation (copied from pipeline.py) ───────────────
# Keep this in sync with pipeline.py whenever summarisation logic changes.

try:
    from sumy.parsers.plaintext import PlaintextParser
    from sumy.nlp.tokenizers import Tokenizer
    from sumy.summarizers.luhn import LuhnSummarizer
    _sumy_ready = True
    print('sumy loaded.')
except ImportError:
    _sumy_ready = False
    print('sumy not found — run: pip install sumy nltk')

def summarise(title, description):
    import re
    text = (description or '').strip()
    if not text:
        return title or 'Summary not available.'

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text)
                 if len(s.strip()) > 10]

    if not sentences:
        return f'{title}\n{_truncate(text, max_words=40)}'

    lead = sentences[0]
    rest = sentences[1:]

    if rest:
        body = _truncate(' '.join(rest), max_words=40)
    else:
        lead = title
        body = _truncate(sentences[0], max_words=40)

    return f'{lead}\n{body}'

# ── Main ──────────────────────────────────────────────────
def main():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Fetch all articles (Supabase returns max 1000 rows per request)
    print('Fetching articles from Supabase...')
    all_articles = []
    page_size    = 1000
    offset       = 0
    while True:
        result = (
            sb.table('articles')
            .select('id, title, description, ai_summary')
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = result.data
        all_articles.extend(batch)
        print(f'  Fetched {len(all_articles)} so far...')
        if len(batch) < page_size:
            break   # last page
        offset += page_size

    total = len(all_articles)
    print(f'Total articles to reprocess: {total}\n')

    updated  = 0
    skipped  = 0
    for i, article in enumerate(all_articles, 1):
        title = article.get('title', '')       or ''
        desc  = article.get('description', '') or ''

        new_summary = summarise(title, desc)
        old_summary = (article.get('ai_summary') or '').strip()

        # Skip if the summary didn't change (saves unnecessary DB writes)
        if new_summary == old_summary:
            skipped += 1
            if i % 50 == 0:
                print(f'[{i}/{total}] {skipped} unchanged so far...')
            continue

        sb.table('articles').update(
            {'ai_summary': new_summary}
        ).eq('id', article['id']).execute()

        updated += 1
        word_count = len(new_summary.split())
        print(f'[{i}/{total}] ({word_count}w) {title[:70]}')

    print(f'\nDone. {updated} updated, {skipped} unchanged.')

if __name__ == '__main__':
    main()
