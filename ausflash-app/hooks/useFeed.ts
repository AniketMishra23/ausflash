// useFeed — fetches articles from the AusFlash API.
// Re-fetches automatically whenever `section` changes.

import { useState, useEffect } from 'react';
import { API_URL } from '@/constants/api';

// Shape of a single article row returned by the API.
// Fields mirror the Supabase `articles` table (see schema.sql).
export interface Article {
  id:           string;
  website_name: string; // e.g. "ABC News Australia"
  section:      string; // e.g. "Tech", "Crime"
  title:        string;
  ai_summary:   string; // extractive summary from sumy (pipeline.py)
  description:  string; // raw RSS/Apify description — used as fallback
  url:          string;
  published_at: string; // ISO 8601 timestamp
  age_hours:    number; // hours since published (set at scrape time)
}

export function useFeed(section: string) {
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);

    // 'All' → no section filter, returns mixed feed sorted by published_at
    const url = section === 'All'
      ? `${API_URL}/feed?limit=60`
      : `${API_URL}/feed?section=${encodeURIComponent(section)}&limit=60`;

    fetch(url)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setArticles(data.articles ?? []); // API wraps results in { articles: [...] }
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [section]); // re-run whenever the selected section changes

  return { articles, loading, error };
}
