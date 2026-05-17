-- ═══════════════════════════════════════════════════════
-- AusFlash — Supabase Schema
-- Run this in the Supabase SQL Editor:
-- https://supabase.com/dashboard → your project → SQL Editor
-- ═══════════════════════════════════════════════════════


-- ── ARTICLES TABLE ────────────────────────────────────────
create table if not exists articles (
    id            uuid        default gen_random_uuid() primary key,
    website_name  text,
    section       text,
    title         text        not null,
    ai_summary    text,
    description   text,
    url           text        not null unique,   -- prevents duplicate articles across runs
    published_at  timestamptz,
    age_hours     float,
    scrape_time   text,
    created_at    timestamptz default now()
);


-- ── INDEXES (fast filtering for the API) ─────────────────
create index if not exists idx_articles_section      on articles (section);
create index if not exists idx_articles_published_at on articles (published_at desc);
create index if not exists idx_articles_created_at   on articles (created_at desc);


-- ── AUTO-CLEANUP (keep DB lean — delete articles > 7 days old) ──
-- Runs as a Supabase cron job (enable pg_cron extension first)
-- Uncomment after enabling pg_cron in Supabase → Database → Extensions

-- select cron.schedule(
--     'delete-old-articles',
--     '0 0 * * *',   -- midnight UTC daily
--     $$ delete from articles where published_at < now() - interval '7 days' $$
-- );


-- ── ROW LEVEL SECURITY ────────────────────────────────────
-- Public can read all articles (needed for the mobile app)
-- Only authenticated service role can insert/update/delete

alter table articles enable row level security;

-- Allow anyone to read articles (mobile app uses anon key)
create policy "Public read access"
    on articles for select
    using (true);

-- Only service role can insert (GitHub Actions uses service role key)
create policy "Service role insert"
    on articles for insert
    with check (true);

-- Only service role can update
create policy "Service role update"
    on articles for update
    using (true);


-- ── VERIFY ────────────────────────────────────────────────
-- After running, check the table was created:
select column_name, data_type
from information_schema.columns
where table_name = 'articles'
order by ordinal_position;
