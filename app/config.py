"""
Westerbergen Guest Insights - Configuration & Brand Constants
"""
import os

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
BRAND_DIR = os.path.join(BASE_DIR, "brand")
DB_PATH = os.path.join(BASE_DIR, "westerbergen.db")

LOGO_CMYK = os.path.join(BRAND_DIR, "logo_cmyk.png")
LOGO_WIT = os.path.join(BRAND_DIR, "logo_wit.png")
LOGO_ZWART = os.path.join(BRAND_DIR, "logo_zwart.png")

# --- Brand Colors (from brandbook) ---
COLORS = {
    # Primary palette
    "diep_bosgroen": "#3B4E37",
    "zandgroen": "#A7A158",
    "natuurlijk_beige": "#E2D6C8",
    "heide_paars": "#AE60A2",
    # Secondary palette
    "warm_goud": "#8D6828",
    "schors_bruin": "#60443A",
    "mos_groen": "#9F9368",
    "oranje_bruin": "#C67741",
    # UI helpers
    "wit": "#FFFFFF",
    "licht_beige": "#F5F0EB",
    "tekst_donker": "#2C3E28",
    "tekst_licht": "#6B7B67",
}

# Chart color sequence (for Plotly)
CHART_COLORS = [
    COLORS["diep_bosgroen"],
    COLORS["zandgroen"],
    COLORS["heide_paars"],
    COLORS["mos_groen"],
    COLORS["oranje_bruin"],
    COLORS["warm_goud"],
    COLORS["schors_bruin"],
]

# --- NPS Definitions ---
NPS_PROMOTER_MIN = 9
NPS_PASSIVE_MIN = 7
# detractors: 0-6

# --- Question -> Category mapping ---
VRAAG_CATEGORIE = {
    "Hoe ervaart u de gastvriendelijkheid op het park?": "Park",
    "Hoe beoordeelt u de kind vriendelijkheid van het park?": "Park",
    "Hoe tevreden bent u met de supermarkt op het park?": "Park",
    "Wat vond u van de eetgelegenheden op het park?": "Park",
    "Hoe tevreden bent u met de accommodatie?": "Verblijf",
    "Hoe tevreden bent u met de kampeerplaats?": "Verblijf",
    "Hoe tevreden bent u over de schoonmaak van uw accommodatie?": "Schoonmaak",
    "Hoe tevreden bent u over het sanitair gebouwen/privé sanitair?": "Schoonmaak",
    "Bent u tevreden over de prijs/kwaliteit verhouding van de accommodatie?": "Prijs/Kwaliteit",
    "Bent u tevreden over de prijs/kwaliteit verhouding van de kampeerplaats?": "Prijs/Kwaliteit",
    "Bent u tevreden over de prijs/kwaliteit verhouding van de kampeerplek?": "Prijs/Kwaliteit",
    "Wat is uw algemene oordeel over uw verblijf?": "Algemeen",
    "Algemene review (niet verplicht)": "Algemeen",
}

# Normalized question labels (for display)
VRAAG_LABEL = {
    "Hoe ervaart u de gastvriendelijkheid op het park?": "Gastvriendelijkheid",
    "Hoe beoordeelt u de kind vriendelijkheid van het park?": "Kindvriendelijkheid",
    "Hoe tevreden bent u met de supermarkt op het park?": "Supermarkt",
    "Wat vond u van de eetgelegenheden op het park?": "Eetgelegenheden",
    "Hoe tevreden bent u met de accommodatie?": "Accommodatie",
    "Hoe tevreden bent u met de kampeerplaats?": "Kampeerplaats",
    "Hoe tevreden bent u over de schoonmaak van uw accommodatie?": "Schoonmaak accommodatie",
    "Hoe tevreden bent u over het sanitair gebouwen/privé sanitair?": "Sanitair/Schoonmaak",
    "Bent u tevreden over de prijs/kwaliteit verhouding van de accommodatie?": "Prijs/Kwaliteit",
    "Bent u tevreden over de prijs/kwaliteit verhouding van de kampeerplaats?": "Prijs/Kwaliteit camping",
    "Bent u tevreden over de prijs/kwaliteit verhouding van de kampeerplek?": "Prijs/Kwaliteit camping",
    "Wat is uw algemene oordeel over uw verblijf?": "Algemeen oordeel",
    "Algemene review (niet verplicht)": "Vrije review",
}

# --- Action item department classification keywords ---
DEPARTMENT_KEYWORDS = {
    "TD": [
        "kapot", "stuk", "defect", "lekkage", "lek", "verwarming", "warm water",
        "boiler", "storing", "reparatie", "onderhoud", "deur", "raam", "slot",
        "lamp", "licht", "elektra", "stroom", "wifi", "internet", "tv",
        "kaputt", "defekt", "heizung", "warmwasser", "reparatur",
        "broken", "heating", "repair", "kraan", "douche", "wc", "toilet",
        "airco", "koelkast", "vaatwasser", "oven", "magnetron",
    ],
    "Housekeeping": [
        "schoonmaak", "vies", "vuil", "stof", "schimmel", "haar", "haren",
        "hygien", "onhygiën", "smerig", "rein", "reinig", "beddengoed",
        "handdoek", "afval", "prullenbak", "schmutzig", "dreckig", "sauber",
        "reinigung", "staub", "cleaning", "dirty", "dust", "mold",
        "spinnen", "spin", "insect", "mug", "muggen", "ongedierte",
    ],
    "Front Office": [
        "receptie", "inchecken", "check-in", "uitchecken", "check-out",
        "reservering", "boeking", "communicatie", "informatie", "parkeerplaats",
        "rezeption", "buchung", "reception", "booking", "parkeren",
        "sleutel", "key", "schlüssel", "wachten", "wachttijd",
    ],
    "F&B": [
        "restaurant", "eten", "drinken", "ontbijt", "lunch", "diner",
        "bediening", "menu", "keuken", "bar", "terras", "snackbar",
        "essen", "trinken", "frühstück", "bedienung", "food", "breakfast",
        "koffie", "coffee", "kaffee", "supermarkt", "winkel", "brood",
    ],
    "Recreatie": [
        "zwembad", "zwem", "glijbaan", "speeltuin", "animatie", "activiteit",
        "entertainment", "bowlen", "bowling", "wellness", "sauna", "fitness",
        "schwimmbad", "spielplatz", "animation", "swimming", "pool",
        "trampoline", "klimmen", "sport", "fiets", "fietsen",
    ],
    "Safety/Overlast": [
        "overlast", "lawaai", "herrie", "geluid", "nacht", "veiligheid",
        "onveilig", "gevaarlijk", "brand", "alarm", "lärm", "geräusch",
        "sicherheit", "noise", "safety", "snelheid", "auto", "verkeer",
        "hond", "honden", "dog",
    ],
}

# --- Priority classification keywords ---
PRIORITY_KEYWORDS = {
    "P1": [  # Safety / Hygiene / Direct impact
        "veiligheid", "onveilig", "gevaarlijk", "brand", "alarm", "lekkage",
        "schimmel", "onhygiën", "smerig", "giftig", "sicherheit", "gefährlich",
        "safety", "dangerous", "mold", "elektra", "stroom",
    ],
    "P2": [  # Comfort
        "kapot", "stuk", "defect", "verwarming", "warm water", "koude",
        "wifi", "internet", "tv", "douche", "toilet", "wc", "bed",
        "matras", "geluidsoverlast", "lawaai", "herrie",
    ],
    # P3 = default (improvement opportunity)
}
