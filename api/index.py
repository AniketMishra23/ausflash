"""
AusFlash API — FastAPI backend deployed on Render.
Serves articles stored in Supabase to the mobile app.

Endpoints:
  GET /                          → health check
  GET /feed                      → latest articles (all sections)
  GET /feed?section=Tech         → filter by section
  GET /feed?limit=20&offset=20   → paginate
  GET /sections                  → article counts per section
  GET /article/{id}              → single article by UUID
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import os
from supabase import create_client

app = FastAPI(title="AusFlash API", version="1.0.0")

# ── CORS ──────────────────────────────────────────────────
# Allow any origin so the Expo app (and future web app) can call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],  # read-only API — no POST/PUT/DELETE needed
    allow_headers=["*"],
)

# ── Supabase client ───────────────────────────────────────
# Uses the service role key so it bypasses RLS (safe — API is read-only).
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# Valid section names — must match the values written by pipeline.py
SECTIONS = ["Crime", "Tech", "Politics", "Business", "Science",
            "Sport", "Entertainment", "Lifestyle", "World"]


# ── Health check ──────────────────────────────────────────
@app.get("/")
def health():
    return {"status": "ok", "service": "AusFlash API"}


# ── Main feed ─────────────────────────────────────────────
@app.get("/feed")
def get_feed(
    section: Optional[str] = Query(None, description="Filter by section"),
    limit:   int            = Query(50,  ge=1, le=200),  # cap at 200 to protect DB
    offset:  int            = Query(0,   ge=0),
):
    # Reject unknown section names early so bad queries don't hit the DB
    if section and section not in SECTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown section. Valid: {SECTIONS}")

    # Build the query — description is excluded to keep payload small
    query = (
        sb.table("articles")
        .select("id, website_name, section, title, ai_summary, description, url, published_at, age_hours")
        .order("published_at", desc=True)  # newest first
        .range(offset, offset + limit - 1) # Supabase range is inclusive on both ends
    )
    if section:
        query = query.eq("section", section)

    result = query.execute()
    return {
        "section":  section or "All",
        "count":    len(result.data),
        "offset":   offset,
        "limit":    limit,
        "articles": result.data,
    }


# ── Section counts ────────────────────────────────────────
# Used by the app to show how many articles exist per section.
# One DB query per section — acceptable since there are only 9 sections.
@app.get("/sections")
def get_sections():
    counts = []
    for section in SECTIONS:
        result = (
            sb.table("articles")
            .select("id", count="exact")  # count="exact" returns total without fetching rows
            .eq("section", section)
            .execute()
        )
        counts.append({"section": section, "count": result.count or 0})
    return {"sections": counts}


# ── Single article ────────────────────────────────────────
# Fetches all columns (including full description) for a detail view.
@app.get("/article/{article_id}")
def get_article(article_id: str):
    result = sb.table("articles").select("*").eq("id", article_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Article not found")
    return result.data[0]
