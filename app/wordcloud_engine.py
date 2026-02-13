"""
Westerbergen Guest Insights - Word Cloud & Sentiment Trends Engine
Uses TF-IDF with domain-specific stopwords for meaningful word clouds.
Sentiment analysis powered by nlptown/bert-base-multilingual-uncased-sentiment.
"""
import re
import json
import hashlib
import logging
import subprocess
from io import BytesIO
from pathlib import Path
from collections import Counter

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from wordcloud import WordCloud

from app.config import COLORS

log = logging.getLogger(__name__)

# ============================================================
# BERT Sentiment Model
# ============================================================
# Strategy:
#   1. Direct import (transformers + torch available → Streamlit Cloud or compatible Python)
#   2. Subprocess to Python 3.13 (local Windows with Python 3.14 beta)
#   3. Regex fallback (if neither works)

_SENTIMENT_CACHE: dict[str, str] = {}  # text → "positive"/"negative"/"neutral"
_CACHE_FILE = Path(__file__).parent.parent / "data" / "sentiment_cache.json"
_MODEL_PIPELINE = None  # Lazy-loaded transformers pipeline
_MODEL_MODE = None      # "direct" | "subprocess" | "regex"


def _detect_model_mode() -> str:
    """Detect which sentiment model strategy to use."""
    # Strategy 1: Direct import (Streamlit Cloud, or local with compatible Python)
    try:
        from transformers import pipeline as _  # noqa: F401
        log.info("Sentiment model: using direct transformers import")
        return "direct"
    except Exception:
        pass

    # Strategy 2: Subprocess to Python 3.13 (local Windows)
    python313 = Path(r"C:\Users\Niek\AppData\Local\Python\pythoncore-3.13-64\python.exe")
    if python313.exists():
        log.info("Sentiment model: using subprocess to Python 3.13")
        return "subprocess"

    # Strategy 3: Regex fallback
    log.warning("Sentiment model: falling back to regex (no BERT model available)")
    return "regex"


def _get_direct_pipeline():
    """Get or create the transformers pipeline for direct mode."""
    global _MODEL_PIPELINE
    if _MODEL_PIPELINE is None:
        from transformers import pipeline
        _MODEL_PIPELINE = pipeline(
            "text-classification",
            model="nlptown/bert-base-multilingual-uncased-sentiment",
            device=-1,
            truncation=True,
            max_length=512,
        )
    return _MODEL_PIPELINE


def _classify_batch_direct(texts: list[str]) -> list[dict]:
    """Classify texts using direct transformers import."""
    pipe = _get_direct_pipeline()
    results = []
    batch_size = 32
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        preds = pipe(batch, batch_size=batch_size)
        for pred in preds:
            stars = int(pred["label"].split(" ")[0])
            label = "negative" if stars <= 2 else ("positive" if stars >= 4 else "neutral")
            results.append({"label": label, "stars": stars, "confidence": round(pred["score"], 3)})
    return results


def _classify_batch_subprocess(texts: list[str]) -> list[dict]:
    """Classify texts using subprocess to Python 3.13."""
    python313 = r"C:\Users\Niek\AppData\Local\Python\pythoncore-3.13-64\python.exe"
    worker = str(Path(__file__).parent / "sentiment_model.py")
    payload = json.dumps({"texts": texts}).encode("utf-8")

    proc = subprocess.run(
        [python313, worker],
        input=payload,
        capture_output=True,
        timeout=600,
    )

    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace")[:500])

    response = json.loads(proc.stdout.decode("utf-8"))
    return response.get("results", [])


def _load_sentiment_cache():
    """Load cached sentiment results from disk."""
    global _SENTIMENT_CACHE
    if _CACHE_FILE.exists():
        try:
            with open(_CACHE_FILE, encoding="utf-8") as f:
                _SENTIMENT_CACHE = json.load(f)
            log.info("Loaded %d cached sentiment results", len(_SENTIMENT_CACHE))
        except (json.JSONDecodeError, OSError):
            _SENTIMENT_CACHE = {}


def _save_sentiment_cache():
    """Save sentiment cache to disk."""
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(_SENTIMENT_CACHE, f, ensure_ascii=False)


def _cache_key(text: str) -> str:
    """Create a short cache key from text."""
    return hashlib.md5(text.strip().lower().encode("utf-8")).hexdigest()


def classify_texts_with_model(texts: list[str]) -> list[dict]:
    """
    Classify a batch of texts using the BERT sentiment model.

    Tries three strategies in order:
    1. Direct transformers import (Streamlit Cloud)
    2. Subprocess to Python 3.13 (local Windows)
    3. Regex fallback

    Returns list of {"label": str, "stars": int, "confidence": float}.
    """
    global _MODEL_MODE
    if not texts:
        return []

    # Detect mode on first call
    if _MODEL_MODE is None:
        _MODEL_MODE = _detect_model_mode()

    # Check which texts we already have cached
    uncached_texts = []
    uncached_indices = []
    results = [None] * len(texts)

    for i, text in enumerate(texts):
        key = _cache_key(text)
        if key in _SENTIMENT_CACHE:
            results[i] = {"label": _SENTIMENT_CACHE[key], "stars": 0, "confidence": 1.0}
        else:
            uncached_texts.append(text)
            uncached_indices.append(i)

    if not uncached_texts:
        return results

    log.info("Classifying %d texts with BERT model [%s] (%d cached)",
             len(uncached_texts), _MODEL_MODE, len(texts) - len(uncached_texts))

    # --- Regex fallback mode ---
    if _MODEL_MODE == "regex":
        for idx in uncached_indices:
            label = _classify_sentence_sentiment(texts[idx])
            results[idx] = {"label": label, "stars": 0, "confidence": 0.5}
            _SENTIMENT_CACHE[_cache_key(texts[idx])] = label
        _save_sentiment_cache()
        return results

    # --- BERT model (direct or subprocess) ---
    chunk_size = 500
    all_model_results = []

    for chunk_start in range(0, len(uncached_texts), chunk_size):
        chunk = uncached_texts[chunk_start : chunk_start + chunk_size]
        log.info("  Processing chunk %d-%d of %d...",
                 chunk_start, chunk_start + len(chunk), len(uncached_texts))

        try:
            if _MODEL_MODE == "direct":
                chunk_results = _classify_batch_direct(chunk)
            else:
                chunk_results = _classify_batch_subprocess(chunk)
            all_model_results.extend(chunk_results)

        except Exception as e:
            log.error("Sentiment model error: %s", e)
            # Fall back to regex for this chunk
            for text in chunk:
                label = _classify_sentence_sentiment(text)
                all_model_results.append({"label": label, "stars": 0, "confidence": 0.5})

    # Store results in cache
    for idx, model_result in zip(uncached_indices, all_model_results):
        results[idx] = model_result
        key = _cache_key(texts[idx])
        _SENTIMENT_CACHE[key] = model_result["label"]

    _save_sentiment_cache()
    return results


# Load cache on module import
_load_sentiment_cache()

# ============================================================
# Stopwords: Dutch + German + English + Domain-specific
# ============================================================

# Core Dutch stopwords
_NL_STOP = {
    "de", "het", "een", "en", "van", "in", "is", "dat", "op", "te", "er",
    "zijn", "voor", "met", "niet", "aan", "ook", "als", "maar", "om", "dan",
    "nog", "al", "bij", "uit", "naar", "door", "over", "tot", "werd", "zou",
    "kan", "hun", "dus", "dit", "die", "wat", "was", "wel", "geen", "worden",
    "meer", "veel", "zo", "ze", "we", "je", "ik", "hij", "zij", "wij", "u",
    "mijn", "ons", "onze", "jullie", "jouw", "haar", "hem", "heeft", "had",
    "hebben", "ben", "bent", "heb", "zal", "zullen", "zouden", "kun", "kunnen",
    "mogen", "mag", "moet", "moeten", "wil", "willen", "gaan", "ging", "gegaan",
    "komt", "komen", "kwam", "gekomen", "wordt", "werden", "geworden",
    "daar", "hier", "waar", "wanneer", "hoe", "wie", "welke", "alle", "iets",
    "niets", "alles", "andere", "ander", "eigen", "eerste", "twee", "drie",
    "nieuwe", "grote", "kleine", "hele", "erg", "heel", "zeer", "best",
    "toch", "weer", "eens", "even", "alleen", "altijd", "vaak", "soms",
    "na", "onder", "boven", "tussen", "tijdens", "sinds", "zonder", "tegen",
}

# Core German stopwords
_DE_STOP = {
    "der", "die", "das", "ein", "eine", "und", "in", "ist", "von", "zu",
    "den", "mit", "auf", "für", "nicht", "sich", "des", "dem", "dass",
    "es", "auch", "als", "an", "aus", "wie", "oder", "aber", "hat", "war",
    "bei", "nach", "noch", "nur", "so", "wenn", "kann", "schon", "sein",
    "seine", "seine", "sind", "wird", "haben", "hatte", "sehr", "wir",
    "ich", "sie", "er", "man", "was", "mir", "mich", "dir", "uns", "ihr",
    "ihm", "mein", "dein", "kein", "keine", "diesem", "dieser", "dieses",
    "jeder", "alle", "alles", "etwas", "nichts", "viel", "mehr", "immer",
    "dann", "da", "hier", "wo", "wann", "warum", "durch", "über", "unter",
    "zwischen", "vor", "nach", "zum", "zur",
}

# Core English stopwords
_EN_STOP = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "is", "was", "are", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "not", "no", "nor", "so",
    "if", "then", "than", "that", "this", "these", "those", "it", "its",
    "we", "our", "you", "your", "they", "them", "their", "he", "she",
    "him", "her", "his", "i", "me", "my", "what", "which", "who", "when",
    "where", "how", "why", "all", "each", "every", "some", "any", "few",
    "more", "most", "other", "into", "up", "out", "about", "just", "very",
    "really", "also", "too", "much", "many", "only", "well", "still",
    "from", "over", "after", "before", "between", "through",
}

# Domain-specific stopwords (words that appear everywhere in hospitality reviews)
_DOMAIN_STOP = {
    # Generic hospitality
    "vakantie", "verblijf", "park", "westerbergen", "accommodatie", "gast",
    "gasten", "keer", "keren", "dag", "dagen", "week", "weken", "nacht",
    "nachten", "jaar", "jaren", "reservering", "boeking",
    # Generic review language
    "goed", "prima", "fijn", "leuk", "mooi", "lekker", "gezellig", "super",
    "top", "fantastisch", "geweldig", "uitstekend", "prima", "okee", "ok",
    "oke", "okay", "gaat", "vond", "vinden", "vinden", "hadden", "gehad",
    # Generic verbs/adjectives in reviews
    "gebruik", "gebruikt", "gemaakt", "gedaan", "gezien", "gevonden",
    "geweest", "goed", "beter", "beste",
    # Numbers / time
    "uur", "minuten", "kamer", "kamers",
    # German hospitality
    "urlaub", "ferien", "gut", "schön", "toll", "super", "prima",
    # English hospitality
    "good", "nice", "great", "lovely", "wonderful", "amazing", "perfect",
    "stay", "holiday", "vacation", "place", "time",
    # Frequent but non-informative terms found in Westerbergen data
    "huisje", "waren", "echt", "doen", "gedaan", "konden", "helemaal",
    "laten", "weten", "verder", "mooie", "mooi", "zeker", "gewoon",
    "beetje", "natuurlijk", "precies", "helaas", "jammer", "alweer",
    "konden", "kende", "steeds", "komen", "lekker", "gegeten",
}

ALL_STOPWORDS = _NL_STOP | _DE_STOP | _EN_STOP | _DOMAIN_STOP


# ============================================================
# Text preprocessing
# ============================================================

def _clean_text(text: str) -> str:
    """Clean a single review text for analysis."""
    if not text or not isinstance(text, str):
        return ""
    text = text.lower()
    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)
    # Remove email addresses
    text = re.sub(r"\S+@\S+", "", text)
    # Remove numbers (standalone)
    text = re.sub(r"\b\d+\b", "", text)
    # Keep only letters, spaces, hyphens
    text = re.sub(r"[^a-záàâäãéèêëíìîïóòôöõúùûüñçß\s-]", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_texts(df: pd.DataFrame) -> pd.Series:
    """Extract meaningful review texts from a DataFrame."""
    texts = []
    for _, row in df.iterrows():
        aanvulling = str(row.get("aanvulling", "")).strip()
        antwoord = str(row.get("antwoord", "")).strip()

        # Use aanvulling first; fall back to antwoord if it's free text
        if aanvulling and aanvulling.lower() not in ("nan", ""):
            texts.append(aanvulling)
        elif antwoord and antwoord.lower() not in ("nan", "") and not antwoord.replace(".", "").isdigit():
            texts.append(antwoord)
        else:
            texts.append("")

    return pd.Series(texts, index=df.index)


# ============================================================
# TF-IDF extraction
# ============================================================

def extract_tfidf_terms(texts: list[str], top_n: int = 40) -> dict[str, float]:
    """
    Extract top-N terms using TF-IDF scores.
    Returns dict of {term: tfidf_score}.
    Uses unigrams + bigrams, filters stopwords.
    """
    # Clean texts
    cleaned = [_clean_text(t) for t in texts]
    # Filter empty
    cleaned = [t for t in cleaned if len(t) > 5]

    if len(cleaned) < 3:
        return {}

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        max_features=500,
        min_df=2,            # Term must appear in at least 2 docs
        max_df=0.85,         # Ignore terms in >85% of docs (too common)
        stop_words=list(ALL_STOPWORDS),
        token_pattern=r"(?u)\b[a-záàâäãéèêëíìîïóòôöõúùûüñçß]{2,}\b",
    )

    try:
        tfidf_matrix = vectorizer.fit_transform(cleaned)
    except ValueError:
        return {}

    feature_names = vectorizer.get_feature_names_out()

    # Sum TF-IDF scores across all documents per term
    scores = tfidf_matrix.sum(axis=0).A1
    term_scores = dict(zip(feature_names, scores))

    # Sort by score and return top N
    sorted_terms = sorted(term_scores.items(), key=lambda x: x[1], reverse=True)
    return dict(sorted_terms[:top_n])


# ============================================================
# Word cloud generation
# ============================================================

def generate_wordcloud_image(
    term_scores: dict[str, float],
    color_palette: str = "positive",
    width: int = 800,
    height: int = 400,
) -> bytes | None:
    """
    Generate a word cloud PNG from term scores.
    Returns PNG bytes or None if insufficient data.
    """
    if not term_scores or len(term_scores) < 3:
        return None

    # Color functions for brand palette
    if color_palette == "positive":
        colors = ["#3B4E37", "#5A7A54", "#7A9A6E", "#A7A158", "#9F9368"]
    else:
        colors = ["#AE60A2", "#8B3A7D", "#C67741", "#60443A", "#9E4E8A"]

    def _color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        idx = hash(word) % len(colors)
        return colors[idx]

    wc = WordCloud(
        width=width,
        height=height,
        background_color=None,
        mode="RGBA",
        font_path=None,  # Uses default (DejaVu Sans — clean, readable)
        prefer_horizontal=0.8,
        max_words=40,
        min_font_size=12,
        max_font_size=80,
        relative_scaling=0.5,
        color_func=_color_func,
        margin=10,
    )

    wc.generate_from_frequencies(term_scores)

    # Export as PNG bytes
    buf = BytesIO()
    wc.to_image().save(buf, format="PNG")
    return buf.getvalue()


# ============================================================
# Trending topics over time
# ============================================================

def compute_trending_topics(
    df: pd.DataFrame,
    n_months: int = 6,
    top_n: int = 8,
) -> pd.DataFrame:
    """
    Compute term frequency per month for trending analysis.
    Returns DataFrame with columns: maand_label, term, count.
    """
    if df.empty or "ingevuld_op" not in df.columns:
        return pd.DataFrame()

    # Need year+month
    df = df.copy()
    df["_datum"] = pd.to_datetime(df["ingevuld_op"], errors="coerce")
    df = df[df["_datum"].notna()]
    df["_ym"] = df["_datum"].dt.to_period("M")

    # Get recent N months
    periods = sorted(df["_ym"].dropna().unique())
    if len(periods) < 2:
        return pd.DataFrame()
    recent_periods = periods[-n_months:]

    texts_series = _extract_texts(df)

    # First, find globally important terms using TF-IDF across ALL texts
    all_texts = texts_series[texts_series.str.len() > 5].tolist()
    global_terms = extract_tfidf_terms(all_texts, top_n=30)

    if not global_terms:
        return pd.DataFrame()

    # Now count these terms per month
    rows = []
    for period in recent_periods:
        period_mask = df["_ym"] == period
        period_texts = texts_series[period_mask]

        # Count term occurrences
        combined = " ".join(_clean_text(t) for t in period_texts if isinstance(t, str))
        combined_lower = combined.lower()

        for term in global_terms:
            count = combined_lower.count(term)
            rows.append({
                "maand_label": str(period),
                "term": term,
                "count": count,
            })

    trend_df = pd.DataFrame(rows)

    if trend_df.empty:
        return trend_df

    # Calculate trend: compare last 2 months avg vs earlier avg
    if len(recent_periods) >= 4:
        recent_2 = [str(p) for p in recent_periods[-2:]]
        earlier = [str(p) for p in recent_periods[:-2]]

        recent_avg = trend_df[trend_df["maand_label"].isin(recent_2)].groupby("term")["count"].mean()
        earlier_avg = trend_df[trend_df["maand_label"].isin(earlier)].groupby("term")["count"].mean()

        # Compute delta
        deltas = (recent_avg - earlier_avg).sort_values(ascending=False)

        # Top rising terms
        rising = deltas.head(top_n).index.tolist()

        # Filter trend_df to only these terms
        trend_df = trend_df[trend_df["term"].isin(rising)]

    return trend_df


def compute_term_summary(
    df_positive: pd.DataFrame,
    df_negative: pd.DataFrame,
    top_n: int = 25,
) -> pd.DataFrame:
    """
    Create a summary table of terms with frequency, sentiment split, and trend indicator.
    Returns DataFrame with: term, mentions_pos, mentions_neg, total, sentiment, trend_icon.
    """
    pos_texts = _extract_texts(df_positive)
    neg_texts = _extract_texts(df_negative)

    # Count terms in positive reviews
    pos_all = " ".join(_clean_text(t) for t in pos_texts if isinstance(t, str) and len(str(t).strip()) > 3)
    neg_all = " ".join(_clean_text(t) for t in neg_texts if isinstance(t, str) and len(str(t).strip()) > 3)

    # Get important terms from both
    all_combined = pos_all + " " + neg_all
    all_terms_list = [w for w in all_combined.split() if w not in ALL_STOPWORDS and len(w) > 2]

    if not all_terms_list:
        return pd.DataFrame()

    term_counts = Counter(all_terms_list)
    top_terms = [t for t, _ in term_counts.most_common(80)]

    # Now count each term in positive and negative
    rows = []
    for term in top_terms:
        pos_count = pos_all.lower().count(term)
        neg_count = neg_all.lower().count(term)
        total = pos_count + neg_count

        if total < 3:
            continue

        # Determine sentiment balance
        if total > 0:
            pos_ratio = pos_count / total
            if pos_ratio >= 0.7:
                sentiment = "Positief"
            elif pos_ratio <= 0.3:
                sentiment = "Negatief"
            else:
                sentiment = "Neutraal"
        else:
            sentiment = "Neutraal"

        rows.append({
            "Term": term.capitalize(),
            "Positief": pos_count,
            "Negatief": neg_count,
            "Totaal": total,
            "Sentiment": sentiment,
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values("Totaal", ascending=False).head(top_n)
    return result


# ============================================================
# Sentence-level sentiment for aspect analysis
# ============================================================

# --- Negation patterns ---
# These FLIP sentiment: "niet" + positive word = negative, "niet" + negative word = positive
# Matched BEFORE individual signal words so they take priority.
# Each tuple: (pattern, resulting_sentiment)
_NEGATION_POSITIVE = [
    # "niet/geen" + negative = actually positive (litotes)
    # "niet te klagen" = positive, "niet te missen" = positive
    (r"\bniet\s+te\s+klagen\b", "positive"),
    (r"\bniet\s+te\s+missen\b", "positive"),
    (r"\bniet\s+te\s+overtreffen\b", "positive"),
    (r"\bkon\s+niet\s+beter\b", "positive"),
    (r"\bkan\s+niet\s+beter\b", "positive"),
    (r"\bkunnen\s+niet\s+beter\b", "positive"),
    (r"\bniet\s+stuk\s+te\s+krijgen\b", "positive"),
    (r"\bniet\s+kapot\s+te\s+krijgen\b", "positive"),
    (r"\bniet\s+vriendelijker\b", "positive"),     # kon niet vriendelijker
    (r"\bniet\s+beter\s+kunnen\b", "positive"),
    (r"\bgeen\s+klachten\b", "positive"),
    (r"\bgeen\s+aanmerkingen\b", "positive"),
    (r"\bniks\s+te\s+klagen\b", "positive"),
    (r"\bniets\s+te\s+klagen\b", "positive"),
    (r"\bniks\s+op\s+aan\s+te\s+merken\b", "positive"),
    (r"\bniets\s+op\s+aan\s+te\s+merken\b", "positive"),
]

_NEGATION_NEGATIVE = [
    # "niet/geen" + positive = actually negative
    # "niet schoon" = negative, "niet goed" = negative
    (r"\bniet\s+schoon\b", "negative"),
    (r"\bniet\s+goed\b", "negative"),
    (r"\bniet\s+fris\b", "negative"),
    (r"\bniet\s+warm\b", "negative"),
    (r"\bniet\s+leuk\b", "negative"),
    (r"\bniet\s+fijn\b", "negative"),
    (r"\bniet\s+netjes\b", "negative"),
    (r"\bniet\s+heel\b", "negative"),
    (r"\bniet\s+lekker\b", "negative"),
    (r"\bniet\s+prettig\b", "negative"),
    (r"\bniet\s+gezellig\b", "negative"),
    (r"\bniet\s+comfortabel\b", "negative"),
    (r"\bniet\s+modern\b", "negative"),
    (r"\bniet\s+vriendelijk\b", "negative"),
    (r"\bniet\s+behulpzaam\b", "negative"),
    (r"\bgeen\s+warm\s+water\b", "negative"),
    (r"\bniet\s+genoeg\b", "negative"),
    (r"\bniet\s+voldoende\b", "negative"),
    (r"\bniet\s+meer\s+van\s+deze\s+tijd\b", "negative"),
    (r"\bniet\s+kunnen\b", "negative"),
    (r"\bniet\s+konden\b", "negative"),
    (r"\bkon\w*\s+niet\b", "negative"),     # konden niet, kon niet
    (r"\bkun\w*\s+niet\b", "negative"),     # kunnen niet, kun niet
    (r"\bniet\s+mogelijk\b", "negative"),
    (r"\bniet\s+beschikbaar\b", "negative"),
    (r"\bniet\s+aanwezig\b", "negative"),
    (r"\bniet\s+werkend\b", "negative"),
    (r"\bniet\s+werkte\b", "negative"),
    (r"\bwerkt\s+niet\b", "negative"),
    (r"\bwerkte\s+niet\b", "negative"),
    (r"\bgeen\s+gebruik\b", "negative"),
]

# --- Signal words ---
# "niet" removed from _NEGATIVE_SIGNALS — handled by negation patterns above
# "schoon" removed from _POSITIVE_SIGNALS — it's an aspect keyword for Schoonmaak
# "warm"/"koud" removed — ambiguous without context (warm water vs warm weer)
# "oud" removed from negatives — ambiguous (old guests vs old furniture)
_NEGATIVE_SIGNALS = {
    "geen", "nooit", "slecht", "matig", "vies", "vuil", "smerig",
    "kapot", "stuk", "defect", "verouderd", "gedateerd",
    "ijskoud", "vreselijk", "verschrikkelijk", "teleurstellend", "teleurstelling",
    "jammer", "helaas", "tegenvallen", "tegenviel", "tegenvalt",
    "saai", "te klein", "te weinig", "onvoldoende",
    "missen", "miste", "misten", "ontbreekt", "ontbreken",
    "lelijk", "raar", "stinken", "stank", "niks", "niets",
    "probleem", "problemen", "klacht", "storing",
    "lastig", "moeilijk", "irritant", "vervelend",
    "gebroken", "lekt", "lekkage", "lek", "beschadigd",
    "eng", "gevaarlijk", "onveilig", "glad",
    "slordig", "rommelig", "stoffig", "bedompt",
    "duur", "te duur", "prijzig", "overprijsd",
    "wachten", "lang wachten",
    # German negatives
    "schlecht", "kalt", "kaputt", "dreckig", "schmutzig",
    "enttäuschend", "langweilig", "leider", "schade",
}

_POSITIVE_SIGNALS = {
    "goed", "prima", "mooi", "fijn", "heerlijk", "lekker", "fantastisch",
    "geweldig", "uitstekend", "top", "super", "prachtig", "schitterend",
    "perfect", "ideaal", "gezellig", "ruim", "netjes",
    "nieuw", "modern", "comfortabel", "aanrader",
    "tevreden", "blij", "genoten", "genieten", "leuk", "tof",
    "vriendelijk", "behulpzaam", "gastvrij", "smakelijk",
    "verzorgd", "keurig", "uitstekend", "voortreffelijk",
    # German positives
    "gut", "schön", "toll", "wunderbar", "gemütlich", "sauber", "neu",
}


# Pre-compile all regex patterns at module load for performance
_COMPILED_NEG_POS = [re.compile(p) for p, _ in _NEGATION_POSITIVE]
_COMPILED_NEG_NEG = [re.compile(p) for p, _ in _NEGATION_NEGATIVE]

# Split signal words: single words use fast set lookup, multi-word use regex
_NEG_SINGLE = {w for w in _NEGATIVE_SIGNALS if " " not in w}
_NEG_MULTI = [re.compile(rf"\b{re.escape(w)}\b") for w in _NEGATIVE_SIGNALS if " " in w]
_POS_SINGLE = {w for w in _POSITIVE_SIGNALS if " " not in w}
_POS_MULTI = [re.compile(rf"\b{re.escape(w)}\b") for w in _POSITIVE_SIGNALS if " " in w]


def _classify_sentence_sentiment(sentence: str) -> str:
    """
    Classify a sentence as 'positive', 'negative', or 'neutral'.

    Uses pre-compiled patterns and set-based lookups for performance.
    Positive negation patterns (weight 3) beat negative ones (weight 2)
    which beat individual signal words (weight 1).
    """
    s = sentence.lower().strip()

    neg_score = 0
    pos_score = 0

    # Step 1: Positive negation patterns (weight 3)
    for pattern in _COMPILED_NEG_POS:
        if pattern.search(s):
            pos_score += 3

    # Step 2: Negative negation patterns (weight 2)
    for pattern in _COMPILED_NEG_NEG:
        if pattern.search(s):
            neg_score += 2

    # Step 3: Individual signal words — fast set lookup for single words
    words = set(re.findall(r'\b\w+\b', s))
    neg_score += len(words & _NEG_SINGLE)
    pos_score += len(words & _POS_SINGLE)

    # Multi-word signals (e.g. "te klein", "lang wachten") — regex
    for pattern in _NEG_MULTI:
        if pattern.search(s):
            neg_score += 1
    for pattern in _POS_MULTI:
        if pattern.search(s):
            pos_score += 1

    if neg_score > pos_score:
        return "negative"
    elif pos_score > neg_score:
        return "positive"
    return "neutral"


def _get_aspect_text_sentiment(text: str, aspect: str) -> str:
    """
    Determine the sentiment of an aspect mention WITHIN the text.

    Splits text into sentences, finds sentences containing aspect keywords,
    and classifies those specific sentences. This way, a review with score 10
    that says "zwembad was te klein" correctly classifies as negative for Zwembad.

    Returns 'positive', 'negative', or 'neutral'.
    """
    if not text or not isinstance(text, str):
        return "neutral"

    keywords = ASPECT_KEYWORDS.get(aspect, [])
    if not keywords:
        return "neutral"

    text_lower = text.lower()

    # Split into sentences (by period, exclamation, question mark, or semicolon)
    sentences = re.split(r'[.!?;]\s*', text_lower)
    # Also handle comma-separated clauses for short texts
    if len(sentences) <= 1:
        sentences = re.split(r'[.!?;,]\s*', text_lower)

    # Find sentences mentioning this aspect
    aspect_sentences = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        for kw in keywords:
            if kw in sent:
                aspect_sentences.append(sent)
                break

    if not aspect_sentences:
        return "neutral"

    # Classify each aspect-related sentence
    neg = 0
    pos = 0
    for sent in aspect_sentences:
        s = _classify_sentence_sentiment(sent)
        if s == "negative":
            neg += 1
        elif s == "positive":
            pos += 1

    if neg > pos:
        return "negative"
    elif pos > neg:
        return "positive"
    return "neutral"


# ============================================================
# Aspect-based sentiment analysis
# ============================================================

# Aspect categories — 10 categories aligned with MT/directie priorities
# Each category maps to clear organisational responsibility.
# "oud" removed (too ambiguous), "buiten" removed (too broad),
# Wellness/Sauna removed (does not exist on the park),
# German keywords added to capture ~17% German-language reviews.
ASPECT_KEYWORDS = {
    "Schoonmaak": [
        "schoonmaak", "schoon", "vies", "vuil", "stof", "smerig", "schimmel",
        "spinnen", "spinnenwebben", "haar", "haren", "hygien", "stofzuig",
        "schoongemaakt", "poets", "reinig",
        # German
        "sauber", "dreckig", "schmutzig", "staub", "reinigung", "putzen",
    ],
    "Badkamer & Sanitair": [
        # Accommodatie: badkamer in huisje/bungalow
        "badkamer", "douche", "toilet", "wc", "kraan", "wastafel",
        "douchekop", "warm water", "afvoer", "jacuzzi",
        # Camping: sanitairgebouw / privé sanitair
        "sanitair", "sanitairgebouw", "toiletgebouw", "douchegebouw",
        "campingtoilet", "campingdouche", "wasruimte",
        # German
        "badezimmer", "dusche", "toilette", "waschbecken", "warmwasser",
        "sanitärgebäude", "sanitär",
    ],
    "Slaapcomfort & Inventaris": [
        # Bedden & slaapkwaliteit
        "bedden", "matras", "matrassen", "kussen", "slaapkamer", "slapen",
        "beddengoed", "dekbed", "lakens", "slaapcomfort", "hoofdkussen",
        # Keuken & inventaris van de accommodatie
        "keuken", "pannen", "borden", "bestek", "koelkast", "vaatwasser",
        "magnetron", "oven", "kook", "inventaris", "servies",
        # German
        "bett", "betten", "matratze", "kissen", "schlafzimmer", "schlafen",
        "küche", "geschirr", "kühlschrank", "besteck",
    ],
    "Onderhoud & Techniek": [
        # Staat van de accommodatie / technische zaken
        "onderhoud", "verouderd", "kapot", "stuk", "defect",
        "reparatie", "slijtage", "gedateerd", "achterstallig",
        "roest", "verf", "tocht",
        # Wifi & technische installaties
        "wifi", "internet", "tv", "televisie", "stroom", "elektra",
        "verwarming", "airco",
        # German
        "kaputt", "defekt", "reparatur", "veraltet", "heizung",
        "fernseher", "strom",
    ],
    "Restaurant & Horeca": [
        "restaurant", "eten", "ontbijt", "diner", "lunch", "bediening",
        "menu", "koffie", "snackbar", "terras", "brood",
        # German
        "essen", "frühstück", "abendessen", "mittagessen", "speisekarte",
        "kaffee", "bedienung", "terrasse",
    ],
    "Personeel & Service": [
        # Personeel, receptie, service-ervaring
        "personeel", "receptie", "vriendelijk", "behulpzaam", "service",
        "medewerk", "inchecken", "check-in", "ontvangst", "gastvrij",
        # Aankomst & vertrek (valt onder front office)
        "aankomst", "vertrek", "inchecktijd", "check-out", "uitchecken",
        "eindschoonmaak", "sleutel", "sleutels", "aankomsttijd",
        "vertrekdag", "oplevering",
        # German
        "personal", "rezeption", "freundlich", "hilfsbereit",
        "ankunft", "abreise", "schlüssel",
    ],
    "Zwembad": [
        "zwembad", "zwemmen", "glijbaan", "glijbanen", "waterglijbaan",
        "zwemparadijs", "binnenbad", "buitenbad", "zwemwater",
        # German
        "schwimmbad", "schwimmen", "rutsche", "wasserrutsche",
        "hallenbad", "freibad",
    ],
    "Animatie & Recreatie": [
        "speeltuin", "trampoline", "bowlen", "bowling", "fitness",
        "animatie", "activiteit", "activiteiten", "klimmen", "sport",
        "spelen", "sportsbar", "entertainment", "kinderactiviteit",
        # German
        "spielplatz", "animation", "aktivität", "aktivitäten",
        "klettern", "unterhaltung",
    ],
    "Prijs & Waarde": [
        "prijs", "duur", "kosten", "geld", "betaal", "goedkoop", "waarde",
        "kwaliteit verhouding", "prijs kwaliteit",
        # German
        "preis", "teuer", "kosten", "geld", "günstig", "wert",
        "preis leistung",
    ],
    "Omgeving & Beleving": [
        # Natuur & omgeving
        "natuur", "bos", "omgeving", "wandel", "fiets", "rust", "rustig",
        "tuin", "groen", "heide",
        # Geluid & overlast
        "geluid", "lawaai", "herrie", "overlast", "stilte",
        "buren", "gehorigheid", "gehorig", "muziek", "feest",
        # Honden & huisdieren
        "hond", "honden", "huisdier", "huisdieren", "hondenlosloop",
        "hondenweide", "uitlaat", "poep",
        # German
        "natur", "wald", "umgebung", "wandern", "fahrrad", "ruhe", "ruhig",
        "lärm", "nachbarn", "hund", "hunde", "haustier",
    ],
}


def _score_aspect_relevance(text: str, aspect: str) -> int:
    """
    Score how relevant a text is to a specific aspect.
    Returns the number of keyword matches (higher = more relevant).
    """
    if not text or not isinstance(text, str):
        return 0
    text_lower = text.lower()
    keywords = ASPECT_KEYWORDS.get(aspect, [])
    return sum(1 for kw in keywords if kw in text_lower)


def _get_primary_aspect(text: str) -> str | None:
    """
    Determine the PRIMARY aspect of a text by finding the aspect
    with the most keyword matches. Returns None if no aspect matches.
    """
    if not text or not isinstance(text, str):
        return None
    scores = {}
    for aspect in ASPECT_KEYWORDS:
        score = _score_aspect_relevance(text, aspect)
        if score > 0:
            scores[aspect] = score
    if not scores:
        return None
    return max(scores, key=scores.get)


def _detect_aspects(text: str) -> list[str]:
    """Detect which aspects are mentioned in a text."""
    if not text or not isinstance(text, str):
        return []
    text_lower = text.lower()
    found = []
    for aspect, keywords in ASPECT_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                found.append(aspect)
                break
    return found


# Aspect display icons (kept for potential future use / exports)
ASPECT_ICONS = {
    "Schoonmaak": "🧹",
    "Badkamer & Sanitair": "🚿",
    "Slaapcomfort & Inventaris": "🛏️",
    "Onderhoud & Techniek": "🔧",
    "Restaurant & Horeca": "🍽️",
    "Personeel & Service": "👋",
    "Zwembad": "🏊",
    "Animatie & Recreatie": "🎯",
    "Prijs & Waarde": "💰",
    "Omgeving & Beleving": "🌲",
}


def _precompute_aspect_sentiments(df: pd.DataFrame) -> dict[int, dict[str, str]]:
    """
    Pre-compute text-level sentiment for EVERY (row, aspect) combination in one pass.

    Uses the BERT sentiment model to classify sentences in bulk, then maps
    results back to (row, aspect) pairs.

    Returns dict: {row_index: {aspect_name: sentiment_string}}.
    """
    texts = df["aanvulling"].astype(str).str.strip()

    # Step 1: For each row, find which aspects match and extract relevant sentences
    # sentence_jobs: list of (row_idx, aspect_name, sentence_text)
    sentence_jobs = []
    job_lookup = {}  # (row_idx, aspect) → list of indices into sentence_jobs

    for idx, text in texts.items():
        if not text or text.lower() == "nan":
            continue
        text_lower = text.lower()

        for aspect, keywords in ASPECT_KEYWORDS.items():
            if not any(kw in text_lower for kw in keywords):
                continue

            # Extract sentences containing aspect keywords
            sentences = re.split(r'(?<=[.!?;])\s+', text)
            aspect_sentences = []
            for sent in sentences:
                if any(kw in sent.lower() for kw in keywords):
                    aspect_sentences.append(sent.strip())

            # If no sentence-level match, use full text
            if not aspect_sentences:
                aspect_sentences = [text[:512]]

            key = (idx, aspect)
            job_lookup[key] = []
            for sent in aspect_sentences:
                job_lookup[key].append(len(sentence_jobs))
                sentence_jobs.append(sent)

    if not sentence_jobs:
        return {}

    # Step 2: Deduplicate sentences for efficiency
    unique_sentences = list(set(sentence_jobs))
    sent_to_idx = {s: i for i, s in enumerate(unique_sentences)}

    # Step 3: Classify all unique sentences with BERT in one batch
    model_results = classify_texts_with_model(unique_sentences)
    sent_to_label = {}
    for sent, result in zip(unique_sentences, model_results):
        sent_to_label[sent] = result["label"]

    # Step 4: Map back to (row, aspect) using majority vote across sentences
    output = {}
    for (row_idx, aspect), job_indices in job_lookup.items():
        labels = [sent_to_label.get(sentence_jobs[j], "neutral") for j in job_indices]
        # Majority vote: count pos/neg/neutral
        n_pos = labels.count("positive")
        n_neg = labels.count("negative")
        n_neu = labels.count("neutral")

        if n_neg > n_pos:
            sentiment = "negative"
        elif n_pos > n_neg:
            sentiment = "positive"
        else:
            sentiment = "neutral"

        if row_idx not in output:
            output[row_idx] = {}
        output[row_idx][aspect] = sentiment

    return output


# Module-level cache of precomputed sentiments (set by compute_aspect_sentiment)
_PRECOMPUTED_SENTIMENTS: dict[int, dict[str, str]] = {}


def _get_aspect_sentiment_from_cache(row_idx: int, aspect: str) -> str:
    """Look up sentiment from precomputed cache, fall back to regex if not available."""
    cached = _PRECOMPUTED_SENTIMENTS.get(row_idx, {}).get(aspect)
    if cached is not None:
        return cached
    return "neutral"


def compute_aspect_sentiment(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute aspect-based sentiment from reviews using TEXT-LEVEL analysis.

    Pre-computes sentiment for all rows in one pass, then aggregates per aspect.
    Falls back to review score when text sentiment is neutral.

    Returns DataFrame with columns:
        aspect, positief, negatief, neutraal, totaal, pct_negatief, sentiment_score
    Sorted by most negative first (= needs most attention).
    """
    if df.empty:
        return pd.DataFrame()

    # Pre-compute all sentiments once using BERT model (big performance win)
    global _PRECOMPUTED_SENTIMENTS
    precomputed = _precompute_aspect_sentiments(df)
    _PRECOMPUTED_SENTIMENTS = precomputed  # Store for reuse by other functions

    rows = []
    for aspect, keywords in ASPECT_KEYWORDS.items():
        pattern = "|".join(re.escape(kw) for kw in keywords)
        mask = df["aanvulling"].astype(str).str.lower().str.contains(pattern, na=False, regex=True)
        aspect_indices = df.index[mask]

        if len(aspect_indices) < 3:
            continue

        n_pos = 0
        n_neg = 0
        n_neu = 0

        for idx in aspect_indices:
            # Use precomputed sentiment
            text_sent = precomputed.get(idx, {}).get(aspect, "neutral")
            review_score = df.at[idx, "score"] if pd.notna(df.at[idx, "score"]) else None

            if text_sent == "negative":
                n_neg += 1
            elif text_sent == "positive":
                n_pos += 1
            else:
                if review_score is not None:
                    if review_score >= 8:
                        n_pos += 1
                    elif review_score <= 6:
                        n_neg += 1
                    else:
                        n_neu += 1
                else:
                    n_neu += 1

        total = n_pos + n_neg + n_neu
        if total == 0:
            continue

        pct_neg = round(n_neg / total * 100, 1)
        pct_pos = round(n_pos / total * 100, 1)
        sentiment_score = round((n_pos - n_neg) / total * 100, 1)

        rows.append({
            "aspect": aspect,
            "positief": n_pos,
            "negatief": n_neg,
            "neutraal": n_neu,
            "totaal": total,
            "pct_negatief": pct_neg,
            "pct_positief": pct_pos,
            "sentiment_score": sentiment_score,
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values("pct_negatief", ascending=False)
    return result


def compute_aspect_yoy(df: pd.DataFrame, aspect: str) -> dict | None:
    """
    Year-over-year comparison for a single aspect using TEXT-LEVEL sentiment.

    Uses the same sentence-level analysis as the rest of the engine, with
    review-score as fallback for neutral text. This ensures the YoY comparison
    is consistent with the sentiment shown in the bar chart and quotes.

    Returns dict with current_pct_neg, prev_pct_neg, delta, or None.
    """
    if df.empty or "jaar" not in df.columns:
        return None

    keywords = ASPECT_KEYWORDS.get(aspect, [])
    if not keywords:
        return None

    pattern = "|".join(re.escape(kw) for kw in keywords)
    mask = df["aanvulling"].astype(str).str.lower().str.contains(pattern, na=False, regex=True)
    aspect_df = df[mask].copy()

    if aspect_df.empty:
        return None

    jaren = sorted(aspect_df["jaar"].dropna().unique())
    if len(jaren) < 2:
        return None

    curr_jaar = jaren[-1]
    prev_jaar = jaren[-2]

    def _count_neg_pct(subset):
        n_neg = 0
        total = 0
        for idx, row in subset.iterrows():
            review_score = row["score"] if pd.notna(row.get("score")) else None
            # Use precomputed BERT sentiment from module-level cache
            text_sent = _PRECOMPUTED_SENTIMENTS.get(idx, {}).get(aspect, "neutral")

            total += 1
            if text_sent == "negative":
                n_neg += 1
            elif text_sent == "neutral" and review_score is not None and review_score <= 6:
                n_neg += 1
        return (n_neg / total * 100) if total > 0 else 0.0

    curr = aspect_df[aspect_df["jaar"] == curr_jaar]
    prev = aspect_df[aspect_df["jaar"] == prev_jaar]

    if len(curr) < 3 or len(prev) < 3:
        return None

    curr_neg = _count_neg_pct(curr)
    prev_neg = _count_neg_pct(prev)

    return {
        "curr_jaar": int(curr_jaar),
        "prev_jaar": int(prev_jaar),
        "curr_pct_neg": round(curr_neg, 1),
        "prev_pct_neg": round(prev_neg, 1),
        "delta": round(curr_neg - prev_neg, 1),
    }


def get_aspect_quotes(
    df: pd.DataFrame,
    aspect: str,
    sentiment: str = "negative",
    n: int = 3,
) -> list[dict]:
    """
    Get representative quotes for an aspect, filtered for RELEVANCE and
    TEXT-LEVEL SENTIMENT.

    Uses two layers of intelligence:
    1. RELEVANCE: Only keeps quotes where this aspect is the primary topic
       (most keyword matches vs other aspects), or has ≥2 keyword matches.
    2. TEXT SENTIMENT: Analyzes the sentences around aspect keywords to determine
       if the mention is actually positive or negative — independent of the
       overall review score. This prevents showing "zwembad is te klein" as a
       positive quote just because the review score was 10.

    sentiment: 'negative' or 'positive'
    Returns list of {tekst, score, objectnaam, datum, tekst_sentiment}.
    """
    keywords = ASPECT_KEYWORDS.get(aspect, [])
    if not keywords or df.empty:
        return []

    pattern = "|".join(re.escape(kw) for kw in keywords)
    mask = (
        df["aanvulling"].astype(str).str.lower().str.contains(pattern, na=False, regex=True) &
        df["aanvulling"].notna() &
        (df["aanvulling"].astype(str).str.strip() != "") &
        (df["aanvulling"].astype(str).str.strip().str.lower() != "nan")
    )

    subset = df[mask].copy()
    if subset.empty:
        return []

    # --- RELEVANCE + TEXT SENTIMENT SCORING ---
    scored_rows = []
    for idx, row in subset.iterrows():
        text = str(row["aanvulling"]).strip()
        review_score = row["score"] if pd.notna(row.get("score")) else None

        # Relevance check
        aspect_score = _score_aspect_relevance(text, aspect)
        primary = _get_primary_aspect(text)
        is_relevant = (primary == aspect) or (aspect_score >= 2)

        if not is_relevant:
            continue

        # Use precomputed BERT sentiment from module-level cache
        text_sent = _PRECOMPUTED_SENTIMENTS.get(idx, {}).get(aspect, "neutral")

        scored_rows.append({
            "idx": idx,
            "relevance": aspect_score,
            "text_sentiment": text_sent,
            "review_score": review_score,
        })

    if not scored_rows:
        return []

    scored_df = pd.DataFrame(scored_rows).set_index("idx")

    # Filter by requested sentiment using TEXT sentiment as primary signal,
    # with review score as fallback for neutral text sentiment
    if sentiment == "negative":
        # Include: text says negative, OR text neutral + review score ≤ 6
        keep_mask = (
            (scored_df["text_sentiment"] == "negative") |
            ((scored_df["text_sentiment"] == "neutral") & (scored_df["review_score"].notna()) & (scored_df["review_score"] <= 6))
        )
    else:
        # Include: text says positive, OR text neutral + review score ≥ 8
        keep_mask = (
            (scored_df["text_sentiment"] == "positive") |
            ((scored_df["text_sentiment"] == "neutral") & (scored_df["review_score"].notna()) & (scored_df["review_score"] >= 8))
        )

    scored_df = scored_df[keep_mask]
    if scored_df.empty:
        return []

    # Join back to original data
    result = subset.loc[subset.index.isin(scored_df.index)].copy()
    result["_relevance"] = scored_df["relevance"]
    result["_text_sentiment"] = scored_df["text_sentiment"]

    # Sort: text-sentiment matches first (exact match > fallback), then relevance, then score
    if sentiment == "negative":
        result["_sent_priority"] = (result["_text_sentiment"] == "negative").astype(int)
        result = result.sort_values(
            ["_sent_priority", "_relevance", "score"],
            ascending=[False, False, True],
        )
    else:
        result["_sent_priority"] = (result["_text_sentiment"] == "positive").astype(int)
        result = result.sort_values(
            ["_sent_priority", "_relevance", "score"],
            ascending=[False, False, False],
        )

    quotes = []
    for _, row in result.head(n).iterrows():
        full_text = str(row["aanvulling"]).strip()
        tekst = _extract_relevant_snippet(full_text, aspect, max_chars=250)
        tekst = tekst.encode("utf-8", "replace").decode("utf-8")
        quotes.append({
            "tekst": tekst,
            "score": int(row["score"]) if pd.notna(row["score"]) else None,
            "objectnaam": str(row.get("objectnaam", "")).strip(),
            "datum": str(row.get("ingevuld_op", ""))[:10],
        })
    return quotes


def _extract_relevant_snippet(text: str, aspect: str, max_chars: int = 250) -> str:
    """
    Extract the most relevant snippet from a review for a given aspect.

    Instead of blindly taking the first 250 characters, finds the sentences
    that mention the aspect and returns those. If the whole text is short
    enough, returns it all.
    """
    if not text or len(text) <= max_chars:
        return text

    keywords = ASPECT_KEYWORDS.get(aspect, [])
    if not keywords:
        return text[:max_chars]

    text_lower = text.lower()

    # Split into sentences
    sentences = re.split(r'(?<=[.!?;])\s+', text)
    if len(sentences) <= 1:
        # No sentence breaks — return first max_chars with word boundary
        if len(text) <= max_chars:
            return text
        cut = text[:max_chars].rfind(" ")
        return text[:cut] + "..." if cut > 100 else text[:max_chars] + "..."

    # Find sentences containing aspect keywords
    relevant = []
    for sent in sentences:
        sent_lower = sent.lower()
        if any(kw in sent_lower for kw in keywords):
            relevant.append(sent.strip())

    if not relevant:
        # Fallback: first max_chars
        cut = text[:max_chars].rfind(" ")
        return text[:cut] + "..." if cut > 100 else text[:max_chars] + "..."

    # Build snippet from relevant sentences
    snippet = " ".join(relevant)
    if len(snippet) <= max_chars:
        return snippet

    # Still too long — take the first relevant sentence(s) that fit
    result = ""
    for sent in relevant:
        if len(result) + len(sent) + 1 <= max_chars:
            result = (result + " " + sent).strip() if result else sent
        else:
            break

    if not result:
        # Single sentence is already too long
        cut = relevant[0][:max_chars].rfind(" ")
        return relevant[0][:cut] + "..." if cut > 100 else relevant[0][:max_chars] + "..."

    return result


def compute_aspect_alerts(
    df: pd.DataFrame,
    n_months_recent: int = 1,
    n_months_baseline: int = 3,
    threshold_pct: float = 50.0,
) -> list[dict]:
    """
    Detect aspects where negative mentions have spiked recently.
    Compares last month vs. previous 3 months baseline.

    Returns list of {aspect, recent_count, baseline_avg, change_pct, alert_type}.
    alert_type: 'spike' (significant increase) or 'improvement' (significant decrease).
    """
    if df.empty or "ingevuld_op" not in df.columns:
        return []

    df = df.copy()
    df["_datum"] = pd.to_datetime(df["ingevuld_op"], errors="coerce")
    df = df[df["_datum"].notna()]

    periods = sorted(df["_datum"].dt.to_period("M").dropna().unique())
    if len(periods) < (n_months_recent + n_months_baseline + 1):
        return []

    recent_periods = periods[-n_months_recent:]
    baseline_periods = periods[-(n_months_recent + n_months_baseline):-n_months_recent]

    alerts = []

    for aspect, keywords in ASPECT_KEYWORDS.items():
        pattern = "|".join(re.escape(kw) for kw in keywords)
        aspect_mask = df["aanvulling"].astype(str).str.lower().str.contains(
            pattern, na=False, regex=True
        )
        neg_mask = aspect_mask & (df["score"].notna()) & (df["score"] <= 6)

        # Count negatives per period
        df_neg = df[neg_mask].copy()
        if df_neg.empty:
            continue
        df_neg["_ym"] = df_neg["_datum"].dt.to_period("M")

        recent_count = df_neg[df_neg["_ym"].isin(recent_periods)].shape[0]
        baseline_counts = [
            df_neg[df_neg["_ym"] == p].shape[0] for p in baseline_periods
        ]
        baseline_avg = sum(baseline_counts) / len(baseline_counts) if baseline_counts else 0

        if baseline_avg < 1 and recent_count < 3:
            continue

        if baseline_avg > 0:
            change_pct = ((recent_count - baseline_avg) / baseline_avg) * 100
        elif recent_count > 0:
            change_pct = 999  # New issue
        else:
            continue

        if change_pct >= threshold_pct and recent_count >= 3:
            alerts.append({
                "aspect": aspect,
                "recent_count": recent_count,
                "baseline_avg": round(baseline_avg, 1),
                "change_pct": round(change_pct, 0),
                "alert_type": "spike",
                "recent_period": str(recent_periods[-1]),
            })
        elif change_pct <= -threshold_pct and baseline_avg >= 3:
            alerts.append({
                "aspect": aspect,
                "recent_count": recent_count,
                "baseline_avg": round(baseline_avg, 1),
                "change_pct": round(change_pct, 0),
                "alert_type": "improvement",
                "recent_period": str(recent_periods[-1]),
            })

    # Sort: spikes first (most urgent), then improvements
    alerts.sort(key=lambda x: (0 if x["alert_type"] == "spike" else 1, -abs(x["change_pct"])))
    return alerts
