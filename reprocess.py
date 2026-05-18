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

BULLET_MAX_WORDS = 25

def _trim_bullet(sentence, max_words=BULLET_MAX_WORDS):
    words = sentence.split()
    if len(words) <= max_words:
        return sentence.rstrip('.')
    return ' '.join(words[:max_words]) + '...'

def summarise(title, description):
    import re
    text = (description or '').strip()
    if not text:
        return f'• {title}' if title else 'Summary not available.'

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text)
                 if len(s.strip()) > 10]

    lead       = sentences[0] if sentences else title
    conclusion = sentences[-1] if len(sentences) > 1 else ''
    detail     = ''

    middle = sentences[1:-1] if len(sentences) > 2 else []
    if middle:
        if _sumy_ready and len(middle) > 1:
            try:
                parser     = PlaintextParser.from_string(' '.join(middle), Tokenizer('english'))
                candidates = [str(s) for s in LuhnSummarizer()(parser.document, sentences_count=2)]
                kept       = [s for s in candidates if _word_overlap(s, title) < 0.6]
                if kept:
                    detail = kept[0]
            except Exception:
                pass
        if not detail:
            detail = middle[0]

    if not detail and lead != title:
        detail = lead
        lead   = title

    seen, parts = set(), []
    for sent in [lead, detail, conclusion]:
        if sent and sent not in seen:
            seen.add(sent)
            parts.append(sent)

    return '\n'.join(f'• {_trim_bullet(p)}' for p in parts[:3])

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
