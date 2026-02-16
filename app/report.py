"""
Westerbergen Guest Insights - Weekly Report Generator
Generates HTML reports in exact Westerbergen MT-rapport huisstijl.
Also generates PDF via fpdf2 for download.
"""
import io
import os
import base64
import pandas as pd
from datetime import datetime, timedelta
from fpdf import FPDF
from app.config import COLORS, LOGO_CMYK, LOGO_ZWART, LOGO_WIT, BRAND_DIR
from app.nps import calc_nps, nps_by_group


def _get_logo_base64(path):
    """Read logo file and return base64 encoded string."""
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""


def _format_date_nl(dt):
    """Format date as d-m."""
    if pd.isna(dt):
        return ""
    try:
        return f"{dt.day}-{dt.month}"
    except Exception:
        return str(dt)[:10]


def _delta_html(val, suffix="%"):
    """Return colored delta HTML."""
    if val is None:
        return "n.v.t."
    if val > 0:
        return f'<span class="kpi-delta positive">&#9650; +{val:.1f}{suffix}</span>'
    elif val < 0:
        return f'<span class="kpi-delta negative">&#9660; {val:.1f}{suffix}</span>'
    else:
        return f'<span class="kpi-delta" style="background:#f5f5f5;color:#666;">0.0{suffix}</span>'


def _nps_delta_span(current, previous):
    """Return colored span for NPS delta in tables."""
    if current is None or previous is None:
        return "n.v.t."
    delta = current - previous
    if delta > 0:
        return f'<span class="positive">+{delta:.1f}</span>'
    elif delta < 0:
        return f'<span class="negative">{delta:.1f}</span>'
    else:
        return f'{delta:.1f}'


def _collect_quotes_by_category(week_data):
    """
    Collect all text reviews grouped by vraag_label (survey question).
    Returns OrderedDict: {short_label: [list of {tekst, objectsoort, objectnaam, aankomst, score}]}
    """
    # Get rows with text in aanvulling
    has_text = week_data[
        (week_data["aanvulling"].notna()) &
        (week_data["aanvulling"].astype(str).str.strip() != "")
    ].copy()

    # Also get "Algemene review" rows where antwoord is text
    review_rows = week_data[
        (week_data["vraag"].astype(str).str.contains("Algemene review", case=False, na=False)) &
        (week_data["antwoord"].notna()) &
        (~week_data["antwoord"].astype(str).str.match(r'^\d+\.?\d*$'))
    ].copy()
    if not review_rows.empty:
        review_rows["aanvulling"] = review_rows["antwoord"]
        review_rows["vraag_label"] = "Vrije review"

    combined = pd.concat([has_text, review_rows], ignore_index=True).drop_duplicates(
        subset=["unique_key"], keep="first"
    )

    # Display order and short labels per vraag_label
    label_order = [
        "Gastvriendelijkheid",
        "Kindvriendelijkheid",
        "Eetgelegenheden",
        "Supermarkt",
        "Accommodatie",
        "Kampeerplaats",
        "Schoonmaak accommodatie",
        "Sanitair/Schoonmaak",
        "Prijs/Kwaliteit",
        "Prijs/Kwaliteit camping",
        "Algemeen oordeel",
        "Vrije review",
    ]

    result = {}
    for label in label_order:
        subset = combined[combined["vraag_label"] == label]
        if subset.empty:
            continue
        quotes = []
        for _, row in subset.iterrows():
            quotes.append({
                "tekst": str(row["aanvulling"])[:500],
                "objectsoort": str(row.get("objectsoort", "")),
                "objectnaam": str(row.get("objectnaam", "")),
                "aankomst": row.get("aankomst"),
                "score": row.get("score"),
            })
        result[label] = quotes

    # Catch any rows with unmapped vraag_label
    mapped_labels = set(label_order)
    remaining = combined[~combined["vraag_label"].isin(mapped_labels)]
    if not remaining.empty:
        quotes = []
        for _, row in remaining.iterrows():
            quotes.append({
                "tekst": str(row["aanvulling"])[:500],
                "objectsoort": str(row.get("objectsoort", "")),
                "objectnaam": str(row.get("objectnaam", "")),
                "aankomst": row.get("aankomst"),
                "score": row.get("score"),
            })
        result["Overig"] = quotes

    return result


def generate_html_report(df, jaar, week):
    """
    Generate a full HTML report matching the handmatige MT-rapport format.
    Returns complete HTML string.
    """
    week_data = df[(df["jaar"] == jaar) & (df["week"] == week)]
    prev_year_data = df[(df["jaar"] == jaar - 1) & (df["week"] == week)]

    # Period string
    try:
        week_start = datetime.fromisocalendar(int(jaar), int(week), 1)
        week_end = week_start + timedelta(days=6)
        period_str = f"{week_start.day}-{week_start.month} t/m {week_end.day}-{week_end.month}"
    except (ValueError, TypeError):
        period_str = f"Week {week}, {jaar}"

    # Calculate metrics
    scored = week_data[week_data["score"].notna()]
    n_respondents = scored["reserveringsnummer"].nunique() if "reserveringsnummer" in scored.columns else len(scored)
    n_quotes = ((week_data["aanvulling"].notna()) & (week_data["aanvulling"].astype(str).str.strip() != "")).sum()

    # NPS calculations - Park group
    park_vragen = ["Gastvriendelijkheid", "Eetgelegenheden", "Kindvriendelijkheid", "Supermarkt"]
    verblijf_vragen = ["Accommodatie", "Kampeerplaats", "Prijs/Kwaliteit", "Prijs/Kwaliteit camping",
                       "Schoonmaak accommodatie", "Sanitair/Schoonmaak", "Algemeen oordeel"]

    # NPS per vraag_label, current + previous year
    vraag_nps_curr = {}
    vraag_nps_prev = {}
    for label in scored["vraag_label"].dropna().unique():
        curr_data = scored[scored["vraag_label"] == label]
        prev_data = prev_year_data[prev_year_data["vraag_label"] == label]
        c = calc_nps(curr_data, min_responses=1)
        p = calc_nps(prev_data, min_responses=1)
        if c:
            vraag_nps_curr[label] = c["nps"]
        if p:
            vraag_nps_prev[label] = p["nps"]

    # Overall NPS (based on "Algemeen oordeel" question only – the true NPS question)
    algemeen_curr = scored[scored["vraag_label"] == "Algemeen oordeel"]
    overall_nps_curr = calc_nps(algemeen_curr, min_responses=1)
    prev_scored = prev_year_data[prev_year_data["score"].notna()]
    algemeen_prev = prev_scored[prev_scored["vraag_label"] == "Algemeen oordeel"]
    overall_nps_prev = calc_nps(algemeen_prev, min_responses=1)

    # NPS signals
    signals = []
    # Find biggest YoY improvement
    best_delta = None
    best_delta_label = None
    for label in vraag_nps_curr:
        if label in vraag_nps_prev:
            d = vraag_nps_curr[label] - vraag_nps_prev[label]
            if best_delta is None or d > best_delta:
                best_delta = d
                best_delta_label = label
    if best_delta is not None and best_delta > 0:
        signals.append(f'<span class="positive">Positieve ontwikkeling:</span> {best_delta_label} (+{best_delta:.1f} punten)')

    # Highest NPS
    if vraag_nps_curr:
        top_label = max(vraag_nps_curr, key=vraag_nps_curr.get)
        signals.append(f'Hoogste NPS: {top_label} ({vraag_nps_curr[top_label]:.1f})')
        bottom_label = min(vraag_nps_curr, key=vraag_nps_curr.get)
        signals.append(f'Laagste NPS: {bottom_label} ({vraag_nps_curr[bottom_label]:.1f})')

    # Collect quotes
    quotes_by_cat = _collect_quotes_by_category(week_data)

    # Logo base64
    logo_wit_b64 = _get_logo_base64(LOGO_WIT)
    logo_zwart_b64 = _get_logo_base64(LOGO_ZWART)

    prev_jaar = jaar - 1

    # Build HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
<style>
body {{
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    color: #3B4E37;
    line-height: 1.7;
    margin: 0;
    padding: 0;
    background-color: #f5f5f5;
}}
.container {{
    max-width: 800px;
    margin: 0 auto;
    background-color: #ffffff;
}}
.header {{
    background-color: #3B4E37;
    color: white;
    padding: 50px 30px 40px 30px;
    text-align: center;
    border-radius: 0 0 50% 50% / 30px;
}}
.logo-image {{
    max-width: 180px;
    height: auto;
    margin-bottom: 20px;
    display: block;
    margin-left: auto;
    margin-right: auto;
}}
.tagline {{
    font-size: 14px;
    margin: 15px 0 0 0;
    opacity: 0.9;
    letter-spacing: 0.3px;
}}
.content {{
    padding: 50px 30px;
}}
h1 {{
    font-family: 'Playfair Display', serif;
    color: #3B4E37;
    font-size: 32px;
    font-weight: 400;
    margin: 0 0 10px 0;
    letter-spacing: 0.5px;
}}
h2 {{
    font-family: 'Playfair Display', serif;
    color: #3B4E37;
    font-size: 24px;
    font-weight: 400;
    margin: 50px 0 20px 0;
    border-bottom: 2px solid #E2D6C8;
    padding-bottom: 10px;
}}
h3 {{
    font-family: 'Playfair Display', serif;
    color: #3B4E37;
    font-size: 20px;
    font-weight: 400;
    margin: 35px 0 15px 0;
}}
.subtitle {{
    color: #8D6828;
    font-size: 16px;
    font-style: italic;
    margin: 0 0 30px 0;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 25px 0;
    background-color: white;
}}
th {{
    background-color: #3B4E37;
    color: white;
    padding: 16px;
    text-align: left;
    font-weight: 600;
    font-size: 14px;
    letter-spacing: 0.3px;
}}
td {{
    padding: 14px 16px;
    border-bottom: 1px solid #E2D6C8;
    font-size: 14px;
}}
tr:nth-child(even) {{
    background-color: #F9F7F4;
}}
.metric-box {{
    background: linear-gradient(60deg, #A7A158 0%, #9F9368 100%);
    color: white;
    border-radius: 15px;
    padding: 28px;
    margin: 25px 0;
    box-shadow: 0 4px 10px rgba(59, 78, 55, 0.15);
}}
.metric-box strong {{
    font-size: 19px;
    display: block;
    margin-bottom: 10px;
    letter-spacing: 0.3px;
}}
.delta-large {{
    font-size: 22px;
    font-weight: bold;
}}
.kpi-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin: 30px 0;
}}
.kpi-card {{
    background: white;
    border: 2px solid #E2D6C8;
    border-radius: 15px;
    padding: 25px;
    text-align: center;
}}
.kpi-label {{
    font-size: 13px;
    color: #8D6828;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600;
    margin-bottom: 12px;
}}
.kpi-value {{
    font-family: 'Playfair Display', serif;
    font-size: 36px;
    font-weight: 700;
    color: #3B4E37;
    margin-bottom: 8px;
}}
.kpi-comparison {{
    font-size: 13px;
    color: #666;
    margin-bottom: 10px;
}}
.kpi-delta {{
    font-size: 18px;
    font-weight: bold;
    padding: 8px 16px;
    border-radius: 20px;
    display: inline-block;
}}
.kpi-delta.positive {{
    background-color: #E8F5E9;
    color: #2E7D32;
}}
.kpi-delta.negative {{
    background-color: #FFEBEE;
    color: #C62828;
}}
.positive {{
    color: #A7A158;
    font-weight: bold;
}}
.negative {{
    color: #C67741;
    font-weight: bold;
}}
.citaat {{
    background-color: #F9F7F4;
    border-left: 4px solid #A7A158;
    border-radius: 0 15px 15px 0;
    padding: 18px 22px;
    margin: 20px 0;
    font-style: italic;
    color: #3B4E37;
    line-height: 1.8;
}}
.citaat-meta {{
    font-size: 13px;
    color: #8D6828;
    margin-top: 10px;
    font-style: normal;
    font-weight: 500;
}}
ul {{
    line-height: 2.2;
    color: #3B4E37;
}}
.footer {{
    background-color: #E2D6C8;
    padding: 35px 30px;
    text-align: center;
    color: #3B4E37;
    font-size: 14px;
    margin-top: 50px;
    border-radius: 50% 50% 0 0 / 30px;
}}
.data-badge {{
    display: inline-block;
    background-color: #AE80A2;
    color: white;
    padding: 10px 20px;
    border-radius: 25px;
    font-size: 14px;
    margin: 8px 8px 8px 0;
    font-weight: 500;
}}
@media only screen and (max-width: 600px) {{
    .container {{ width: 100% !important; }}
    .content {{ padding: 30px 20px !important; }}
    .kpi-grid {{ grid-template-columns: 1fr; gap: 15px; }}
    .kpi-value {{ font-size: 28px; }}
    h1 {{ font-size: 26px !important; }}
    h2 {{ font-size: 20px !important; }}
    .metric-box {{ padding: 20px !important; margin: 20px 0 !important; }}
    .logo-image {{ max-width: 150px !important; }}
    table {{ font-size: 12px !important; }}
    th, td {{ padding: 10px !important; }}
    .data-badge {{ font-size: 12px !important; padding: 8px 14px !important; }}
}}
</style>
</head>
<body>
<div class="container">

<div class="header">
"""
    if logo_wit_b64:
        html += f'<img src="data:image/png;base64,{logo_wit_b64}" alt="Westerbergen logo" class="logo-image">\n'
    html += f"""<p class="tagline">Natuurrijk genieten op Westerbergen</p>
</div>
<div class="content">
<h1>MT-Rapport Gasttevredenheid</h1>
<p class="subtitle">Week {week} &ndash; {jaar}</p>
<div style="margin: 30px 0;">
<span class="data-badge">&#128202; {n_respondents} respondenten</span>
<span class="data-badge">&#128172; {n_quotes} citaten</span>
<span class="data-badge">&#128197; {period_str}</span>
</div>
"""

    # --- NPS Gasttevredenheid ---
    html += '<h2>Gasttevredenheid (NPS)</h2>\n'

    # Single overall NPS metric box
    if overall_nps_curr:
        curr_val = overall_nps_curr["nps"]
        if overall_nps_prev:
            prev_val = overall_nps_prev["nps"]
            delta = curr_val - prev_val
            delta_str = f'<span class="delta-large">{"+" if delta > 0 else ""}{delta:.1f}</span>'
            prev_str = f'{prev_jaar}: {prev_val:+.1f}, {delta_str}'
        else:
            prev_str = ""
        html += f"""<div class="metric-box">
<strong>Algemene NPS</strong>
{curr_val:+.1f}{f" ({prev_str})" if prev_str else ""}
</div>\n"""

    # --- NPS Signals ---
    html += '<h2>Belangrijkste NPS-signalen</h2>\n<ul>\n'
    for signal in signals:
        html += f'<li>{signal}</li>\n'
    html += '</ul>\n'

    # --- NPS Park table ---
    html += '<h2>&#127748; NPS-Overzicht: Park</h2>\n'
    html += f"""<table>
<tr><th>Vraag</th><th style="text-align: center; width: 100px;">NPS {prev_jaar}</th><th style="text-align: center; width: 100px;">NPS {jaar}</th><th style="text-align: center; width: 80px;">&Delta; YoY</th></tr>\n"""

    park_vraag_map = {
        "Gastvriendelijkheid": "Hoe ervaart u de gastvriendelijkheid op het park?",
        "Eetgelegenheden": "Wat vond u van de eetgelegenheden op het park?",
        "Kindvriendelijkheid": "Hoe beoordeelt u de kind vriendelijkheid van het park?",
        "Supermarkt": "Hoe tevreden bent u met de supermarkt op het park?",
    }
    for label, full_q in park_vraag_map.items():
        curr = vraag_nps_curr.get(label)
        prev = vraag_nps_prev.get(label)
        curr_str = f'<strong>{curr:.1f}</strong>' if curr is not None else "n.v.t."
        prev_str = f'{prev:.1f}' if prev is not None else "n.v.t."
        delta_str = _nps_delta_span(curr, prev)
        html += f'<tr><td>{full_q}</td><td style="text-align: center;">{prev_str}</td><td style="text-align: center;">{curr_str}</td><td style="text-align: center;">{delta_str}</td></tr>\n'
    html += '</table>\n'

    # --- NPS Verblijf table ---
    html += f'<h2>&#127969; NPS-Overzicht: Verblijf</h2>\n'
    html += f"""<table>
<tr><th>Vraag</th><th style="text-align: center; width: 100px;">NPS {prev_jaar}</th><th style="text-align: center; width: 100px;">NPS {jaar}</th><th style="text-align: center; width: 80px;">&Delta; YoY</th></tr>\n"""

    verblijf_vraag_map = {
        "Accommodatie": "Hoe tevreden bent u met de accommodatie?",
        "Kampeerplaats": "Hoe tevreden bent u met de kampeerplaats?",
        "Prijs/Kwaliteit": "Bent u tevreden over de prijs/kwaliteit verhouding van de accommodatie?",
        "Prijs/Kwaliteit camping": "Bent u tevreden over de prijs/kwaliteit verhouding van de kampeerplaats?",
        "Schoonmaak accommodatie": "Hoe tevreden bent u over de schoonmaak van uw accommodatie?",
        "Sanitair/Schoonmaak": "Hoe tevreden bent u over het sanitair gebouwen/privé sanitair?",
        "Algemeen oordeel": "Wat is uw algemene oordeel over uw verblijf?",
    }
    for label, full_q in verblijf_vraag_map.items():
        if label not in vraag_nps_curr and label not in vraag_nps_prev:
            continue  # Skip questions with no data at all
        curr = vraag_nps_curr.get(label)
        prev = vraag_nps_prev.get(label)
        curr_str = f'<strong>{curr:.1f}</strong>' if curr is not None else "n.v.t."
        prev_str = f'{prev:.1f}' if prev is not None else "n.v.t."
        delta_str = _nps_delta_span(curr, prev)
        html += f'<tr><td>{full_q}</td><td style="text-align: center;">{prev_str}</td><td style="text-align: center;">{curr_str}</td><td style="text-align: center;">{delta_str}</td></tr>\n'
    html += '</table>\n'

    # --- Gastsignalen (quotes by category) ---
    html += '<h2>&#128172; Gastsignalen</h2>\n'

    for cat_name, quotes_list in quotes_by_cat.items():
        html += f'<h3>{cat_name} ({len(quotes_list)} citaten)</h3>\n'
        for q in quotes_list[:10]:  # Max 10 per category
            tekst = q["tekst"]
            meta_parts = []
            if q["objectsoort"]:
                meta_parts.append(q["objectsoort"])
            if q["objectnaam"]:
                meta_parts.append(q["objectnaam"])
            if q["aankomst"] is not None and not pd.isna(q["aankomst"]):
                try:
                    meta_parts.append(f"Aankomst: {q['aankomst'].strftime('%d-%m-%Y')}")
                except Exception:
                    pass
            meta = " &mdash; ".join(meta_parts)
            html += f"""<div class="citaat">
"{tekst}"
<div class="citaat-meta">{meta}</div>
</div>\n"""

    # --- Footer ---
    html += '</div>\n'  # close content
    html += '<div class="footer">\n'
    if logo_zwart_b64:
        html += f'<img src="data:image/png;base64,{logo_zwart_b64}" alt="Westerbergen logo" style="max-width: 120px; height: auto; margin-bottom: 15px;">\n'
    html += f"""<p style="margin: 10px 0 5px 0;"><strong>Westerbergen</strong></p>
<p style="margin: 0; font-size: 13px; opacity: 0.9;">Natuurrijk genieten op Westerbergen</p>
<p style="margin: 20px 0 0 0; font-size: 12px; opacity: 0.7;">Dit rapport is automatisch gegenereerd op basis van gastenqu&ecirc;te-data<br>Verblijven tijdens week {week} ({period_str})</p>
</div>
</div>
</body>
</html>"""

    return html


def generate_theme_pdf(zoekterm, results_df, nps_result, theme_trend_data, obj_counts, review_texts):
    """
    Generate a PDF for Thema Analyse results.
    Returns PDF bytes.
    """
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.alias_nb_pages()
    pdf.add_page()

    # Header
    if os.path.exists(LOGO_ZWART):
        pdf.image(LOGO_ZWART, 10, 8, 50)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(59, 78, 55)
    pdf.cell(0, 10, "Thema Analyse Rapport", align="R")
    pdf.ln(15)
    pdf.set_draw_color(59, 78, 55)
    pdf.set_line_width(0.5)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(8)

    # Title
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(59, 78, 55)
    pdf.cell(0, 12, f'Thema Analyse: "{zoekterm}"', new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(107, 123, 103)
    pdf.cell(0, 8, f"Gegenereerd op {datetime.now().strftime('%d-%m-%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # KPI row
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(59, 78, 55)
    pdf.cell(0, 8, "Overzicht", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    n_total = len(results_df)
    scores = results_df["score"].dropna()
    avg_score = f"{scores.mean():.1f}" if len(scores) > 0 else "-"
    nps_val = f"{nps_result['nps']:+.0f}" if nps_result else "-"

    # KPI badges
    for label, value in [("Aantal meldingen", str(n_total)), ("Gem. Score", avg_score), ("NPS", nps_val)]:
        x = pdf.get_x()
        y = pdf.get_y()
        w = 55
        h = 22
        pdf.set_fill_color(226, 214, 200)
        pdf.rect(x, y, w, h, "F")
        pdf.set_xy(x, y + 3)
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(59, 78, 55)
        pdf.cell(w, 8, value, align="C")
        pdf.set_xy(x, y + 13)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(107, 123, 103)
        pdf.cell(w, 5, label, align="C")
        pdf.set_xy(x + w + 5, y)

    pdf.ln(30)

    # Top accommodations
    if obj_counts is not None and len(obj_counts) > 0:
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(59, 78, 55)
        pdf.cell(0, 8, "Betrokken Accommodaties", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(59, 78, 55)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(120, 7, "Accommodatie", border=1, fill=True)
        pdf.cell(30, 7, "Aantal", border=1, fill=True, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(44, 62, 40)
        for name, count in obj_counts.head(15).items():
            pdf.cell(120, 6, str(name)[:60], border=1)
            pdf.cell(30, 6, str(count), border=1, align="C")
            pdf.ln()
        pdf.ln(5)

    # Reviews
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(59, 78, 55)
    pdf.cell(0, 8, "Reviews", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    for review in review_texts[:20]:
        tekst = review.get("tekst", "")[:300]
        score = review.get("score")
        obj = review.get("objectnaam", "")

        # Quote block
        pdf.set_fill_color(249, 247, 244)
        pdf.set_draw_color(167, 161, 88)
        x = pdf.get_x()
        y = pdf.get_y()

        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(59, 78, 55)
        pdf.multi_cell(0, 4, f'"{tekst}"')

        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(141, 104, 40)
        score_str = f"Score: {int(score)}" if score is not None and not pd.isna(score) else ""
        pdf.cell(0, 4, f"  {score_str} | {obj}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    # Footer
    pdf.set_y(-20)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(107, 123, 103)
    pdf.cell(0, 10, f"Westerbergen Guest Insights | Thema: {zoekterm} | {datetime.now().strftime('%d-%m-%Y')}", align="C")

    return pdf.output()


# Keep backward compatibility
def generate_week_report(df, jaar, week):
    """Generate HTML report (replaces old PDF-only function)."""
    return generate_html_report(df, jaar, week)


def generate_html_summary(df, jaar, week):
    """Generate HTML summary - now returns the full report."""
    return generate_html_report(df, jaar, week)
