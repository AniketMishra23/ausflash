import { useState, useEffect } from 'react';
import { API_URL } from '@/constants/api';

export interface Article {
  id:           string;
  website_name: string;
  section:      string;
  title:        string;
  ai_summary:   string;
  description:  string;
  url:          string;
  published_at: string;
  age_hours:    number;
}

export function useFeed(section: string) {
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);

    const url = section === 'All'
      ? `${API_URL}/feed?limit=60`
      : `${API_URL}/feed?section=${encodeURIComponent(section)}&limit=60`;

    fetch(url)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        setArticles(data.articles ?? []);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [section]);

  return { articles, loading, error };
}
