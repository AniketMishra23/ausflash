from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import os
from supabase import create_client

app = FastAPI(title="AusFlash API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

SECTIONS = ["Crime", "Tech", "Politics", "Business", "Science",
            "Sport", "Entertainment", "Lifestyle", "World"]


# ── Health check ──────────────────────────────────────────
@app.get("/")
def health():
    return {"status": "ok", "service": "AusFlash API"}


# ── Main feed ─────────────────────────────────────────────
# GET /feed                    → all sections, latest 50 articles
# GET /feed?section=Tech       → Tech only
# GET /feed?limit=20&offset=20 → pagination
@app.get("/feed")
def get_feed(
    section: Optional[str] = Query(None, description="Filter by section"),
    limit:   int            = Query(50,  ge=1, le=200),
    offset:  int            = Query(0,   ge=0),
):
    if section and section not in SECTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown section. Valid: {SECTIONS}")

    query = (
        sb.table("articles")
        .select("id, website_name, section, title, ai_summary, url, published_at, age_hours")
        .order("published_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if section:
        query = query.eq("section", section)

    result = query.execute()
    return {
        "section": section or "All",
        "count":   len(result.data),
        "offset":  offset,
        "limit":   limit,
        "articles": result.data,
    }


# ── Sections list with counts ─────────────────────────────
# GET /sections → [{ "section": "Tech", "count": 42 }, ...]
@app.get("/sections")
def get_sections():
    counts = []
    for section in SECTIONS:
        result = (
            sb.table("articles")
            .select("id", count="exact")
            .eq("section", section)
            .execute()
        )
        counts.append({"section": section, "count": result.count or 0})
    return {"sections": counts}


# ── Single article ────────────────────────────────────────
# GET /article/{id}
@app.get("/article/{article_id}")
def get_article(article_id: str):
    result = sb.table("articles").select("*").eq("id", article_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Article not found")
    return result.data[0]
