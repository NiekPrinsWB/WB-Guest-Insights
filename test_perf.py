"""Test performance + snippet extraction."""
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
from app.database import get_connection
from app.wordcloud_engine import (
    compute_aspect_sentiment, get_aspect_quotes, _extract_relevant_snippet,
    ASPECT_ICONS,
)

conn = get_connection()
df = pd.read_sql("SELECT * FROM responses_raw", conn)
conn.close()
df["score"] = pd.to_numeric(df["antwoord"], errors="coerce")

has_text = (
    df["aanvulling"].notna()
    & (df["aanvulling"].astype(str).str.strip() != "")
    & (df["aanvulling"].astype(str).str.strip().str.lower() != "nan")
)
text_data = df[has_text].copy()

# Performance test
print("=== PERFORMANCE TEST ===")
start = time.time()
aspect_df = compute_aspect_sentiment(text_data)
elapsed = time.time() - start
print(f"compute_aspect_sentiment: {elapsed:.2f}s for {len(text_data)} reviews, {len(aspect_df)} aspects")
print()

# Snippet test
print("=== SNIPPET EXTRACTION TEST ===")
long_text = (
    "We hebben een heerlijk weekend gehad. De kinderen vonden het fantastisch. "
    "Het restaurant was uitstekend, de bediening super vriendelijk. "
    "Helaas was het zwembad te klein en koud. De glijbaan was gesloten. "
    "Verder alles top, we komen zeker terug."
)
snippet = _extract_relevant_snippet(long_text, "Zwembad", max_chars=250)
print(f"Full text ({len(long_text)} chars):")
print(f"  {long_text}")
print(f"Snippet for 'Zwembad' ({len(snippet)} chars):")
print(f"  {snippet}")
print()

# Real snippet examples
print("=== REAL QUOTE SNIPPETS ===")
for aspect in ["Zwembad", "Restaurant & Horeca", "Bedden & Slaapcomfort"]:
    icon = ASPECT_ICONS.get(aspect, "")
    print(f"{icon} {aspect} (negative):")
    quotes = get_aspect_quotes(text_data, aspect, "negative", 2)
    for q in quotes:
        t = q['tekst'].encode('ascii', 'replace').decode('ascii')
        print(f"  Score {q['score']} | {q['objectnaam']}")
        print(f"  -> {t}")
        print()
