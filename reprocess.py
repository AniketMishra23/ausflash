"""
AusFlash — One-Time Re-process Script
Re-summarises all existing articles in Supabase using the current
pipeline logic (BART abstractive, extractive fallback).

Run once locally after any summarisation logic change:
  pip install supabase transformers
  pip install torch --index-url https://download.pytorch.org/whl/cpu
  set SUPABASE_URL=your_url
  set SUPABASE_KEY=your_service_role_key
  python reprocess.py

Safe to delete after running.
"""

import os
import re
from supabase import create_client

SUPABASE_URL = "https://numxnyibpcayiikuotzf.supabase.co"
SUPABASE_KEY = "sb_publishable_47AlYmJdgJQaGPBJbGL-3Q_9sd7Qcli"

# ── Summarisation (kept in sync with pipeline.py) ─────────

try:
    from transformers import pipeline as hf_pipeline
    _summarizer = hf_pipeline(
        'summarization',
        model='sshleifer/distilbart-cnn-12-6',
        device=-1,
    )
    _hf_ready = True
    print('BART summarizer loaded.')
except Exception as _e:
    _hf_ready = False
    print(f'BART not available ({_e}) — using extractive fallback.')

def _truncate(text, max_words=65):
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
    s_words = set(sentence.lower().split())
    t_words = set(title.lower().split())
    if not s_words:
        return 0.0
    return len(s_words & t_words) / len(s_words)

def _clean(s):
    return s.strip().rstrip(' .')

def summarise(title, description):
    text = (description or '').strip()
    if not text:
        return title or 'Summary not available.'

    if _hf_ready:
        try:
            combined  = f'{title}. {text}'
            input_len = len(combined.split())
            max_len   = min(90, max(30, input_len // 2))
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
                    if _word_overlap(lead, title) > 0.55:
                        if rest:
                            lead = rest[0]
                            rest = rest[1:]
                        else:
                            return f'{title}\n{_clean(summary)}'
                    body = ' '.join(rest)
                    return f'{lead}\n{body}' if body else f'{title}\n{lead}'
        except Exception as _e:
            print(f'  BART error: {_e} — falling back')

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text)
                 if len(s.strip()) > 10]
    if not sentences:
        return f'{title}\n{_truncate(text, max_words=40)}'

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

# ── Main ──────────────────────────────────────────────────
def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError('Set SUPABASE_URL and SUPABASE_KEY environment variables before running.')
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
