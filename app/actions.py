"""
Westerbergen Guest Insights - Action items engine
Classifies reviews into departmental issues with priority.
"""
import re
import pandas as pd
from app.config import DEPARTMENT_KEYWORDS, PRIORITY_KEYWORDS

# Simple negative sentiment keywords (Dutch + German + English)
NEGATIVE_KEYWORDS = [
    "slecht", "matig", "teleurgesteld", "teleurstelling", "jammer", "helaas",
    "niet goed", "niet fijn", "niet leuk", "niet schoon", "niet tevreden",
    "vreselijk", "verschrikkelijk", "waardeloos", "onacceptabel", "bagger",
    "klacht", "klachten", "probleem", "problemen", "stuk", "kapot",
    "schlecht", "enttäuscht", "enttäuschung", "leider", "nicht gut",
    "schrecklich", "furchtbar", "mangelhaft", "unzufrieden",
    "bad", "poor", "terrible", "awful", "disappointed", "disappointing",
    "horrible", "worst", "unacceptable", "complaint",
    "nooit meer", "nie wieder", "never again",
    "vies", "smerig", "vuil", "stinkt", "stank",
    "schmutzig", "dreckig", "stinkt", "gestank",
]

COMPLAINT_PATTERNS = [
    r"niet\s+\w+\s+(goed|fijn|leuk|schoon|ok|oké)",
    r"had\s+beter\s+(gek|gem)",
    r"laat\s+te\s+wensen\s+over",
    r"kan\s+beter",
    r"moet\s+nodig",
    r"ver\s*onder\s+de\s+maat",
]


def _detect_sentiment(text):
    """Simple negative sentiment detection. Returns True if negative."""
    if not text or not isinstance(text, str):
        return False
    text_lower = text.lower()

    # Check direct negative keywords
    for kw in NEGATIVE_KEYWORDS:
        if kw in text_lower:
            return True

    # Check complaint patterns
    for pattern in COMPLAINT_PATTERNS:
        if re.search(pattern, text_lower):
            return True

    return False


def _classify_department(text):
    """Classify text to one or more departments. Returns list of dept names."""
    if not text or not isinstance(text, str):
        return []
    text_lower = text.lower()
    departments = []

    for dept, keywords in DEPARTMENT_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                departments.append(dept)
                break

    return departments if departments else ["Front Office"]  # Default fallback


def _classify_priority(text, score=None):
    """Classify priority based on text content and score."""
    if not text:
        text = ""
    text_lower = text.lower()

    # P1: safety/hygiene
    for kw in PRIORITY_KEYWORDS.get("P1", []):
        if kw in text_lower:
            return "P1"

    # Score <= 3 is always P1
    if score is not None and not pd.isna(score) and float(score) <= 3:
        return "P1"

    # P2: comfort issues
    for kw in PRIORITY_KEYWORDS.get("P2", []):
        if kw in text_lower:
            return "P2"

    # Score 4-5 tends to be P2
    if score is not None and not pd.isna(score) and float(score) <= 5:
        return "P2"

    # Default P3
    return "P3"


def generate_issues_for_response(row):
    """
    Determine if a response should generate action items.
    Returns a list of issue dicts: [{tekst, afdeling, prioriteit}, ...]
    """
    issues = []

    score = row.get("score")
    aanvulling = row.get("aanvulling", "")
    antwoord = row.get("antwoord", "")

    # The review text is aanvulling, or for "Algemene review" it might be in antwoord
    tekst = str(aanvulling) if aanvulling and str(aanvulling).strip() else ""
    if not tekst and isinstance(antwoord, str) and not antwoord.replace(".", "").isdigit():
        tekst = antwoord

    if not tekst.strip():
        # No text to analyze, but low score still matters
        if score is not None and not pd.isna(score) and float(score) <= 6:
            # Create a generic issue based on question
            vraag = row.get("vraag_label", row.get("vraag", "Onbekend"))
            tekst = f"Lage score ({int(float(score))}) voor: {vraag}"
            dept = _guess_department_from_question(row.get("categorie", ""))
            priority = _classify_priority("", score)
            issues.append({
                "tekst": tekst,
                "afdeling": dept,
                "prioriteit": priority,
            })
        return issues

    # Check triggers: low score OR negative sentiment OR complaint keywords
    is_low_score = score is not None and not pd.isna(score) and float(score) <= 6
    is_negative = _detect_sentiment(tekst)

    if not is_low_score and not is_negative:
        return issues

    # Classify department(s) and priority
    departments = _classify_department(tekst)
    priority = _classify_priority(tekst, score)

    for dept in departments:
        issues.append({
            "tekst": tekst[:500],  # Cap at 500 chars
            "afdeling": dept,
            "prioriteit": priority,
        })

    return issues


def _guess_department_from_question(categorie):
    """Guess department from question category when no text is available."""
    mapping = {
        "Schoonmaak": "Housekeeping",
        "Verblijf": "TD",
        "Park": "Front Office",
        "Prijs/Kwaliteit": "Front Office",
        "Algemeen": "Front Office",
    }
    return mapping.get(categorie, "Front Office")
