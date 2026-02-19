"""
Westerbergen Guest Insights - Main Streamlit Application
"""
import os
import sys
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import datetime, timedelta

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import (
    COLORS, CHART_COLORS, LOGO_CMYK, LOGO_WIT, DATA_DIR, DB_PATH,
)
from app.style import apply_style
from app.database import (
    get_connection, init_db, load_responses, log_ingestion,
)
from app.ingest import ingest_csv
from app.nps import calc_nps, nps_by_group, nps_trend, nps_yoy, leaderboard
from app.report import generate_week_report, generate_html_summary, generate_html_report, generate_theme_pdf
from app.wordcloud_engine import (
    extract_tfidf_terms, generate_wordcloud_image,
    compute_aspect_sentiment, compute_aspect_alerts,
    get_aspect_quotes, compute_aspect_yoy,
)

# ============================================================
# Page config
# ============================================================
st.set_page_config(
    page_title="Westerbergen Guest Insights",
    page_icon="brand/logo_cmyk.png" if os.path.exists("brand/logo_cmyk.png") else None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject custom CSS
st.markdown(apply_style(), unsafe_allow_html=True)


# ============================================================
# Initialize database & load data
# ============================================================
@st.cache_resource
def get_db():
    conn = get_connection()
    init_db(conn)
    conn.close()
    return True


@st.cache_data(ttl=60)
def load_data():
    return load_responses()


get_db()


def refresh_data():
    load_data.clear()


def validate_csv_upload(file_bytes: bytes, segment: str):
    """
    Validate uploaded CSV bytes before ingestion.
    Returns (ok: bool, message: str, row_count: int).
    """
    import io as _io
    required_cols = {
        "Reserveringsnummer", "Relatie", "Aankomst", "Vertrek",
        "Ingevuld op", "Objectsoort", "Objectnaam", "Verhuurmodel",
        "Vraag", "Antwoord",
    }
    try:
        df_check = pd.read_csv(
            _io.BytesIO(file_bytes),
            sep=";",
            encoding="latin-1",
            dtype=str,
            on_bad_lines="skip",
            nrows=5,
        )
    except Exception as e:
        return False, f"Kan bestand niet lezen: {e}", 0

    # Drop trailing unnamed columns
    df_check = df_check.loc[:, ~df_check.columns.str.startswith("Unnamed")]

    missing = required_cols - set(df_check.columns)
    if missing:
        return False, f"Ontbrekende kolommen: {', '.join(sorted(missing))}", 0

    # Count total rows (full parse, but only necessary columns)
    try:
        df_full = pd.read_csv(
            _io.BytesIO(file_bytes),
            sep=";",
            encoding="latin-1",
            dtype=str,
            on_bad_lines="skip",
        )
        df_full = df_full.loc[:, ~df_full.columns.str.startswith("Unnamed")]
        row_count = len(df_full)
    except Exception:
        row_count = 0

    if row_count < 1:
        return False, "Bestand bevat geen datarijen.", 0

    return True, f"Validatie geslaagd: {row_count:,} rijen gevonden.", row_count


def build_week_verification_table(df_loaded: pd.DataFrame):
    """
    Build a verification table for the last 3 ISO weeks using overlap logic.
    Returns a list of dicts: {Week, Jaar, Segment, Respondenten, NPS_Algemeen}.
    """
    from app.nps import calc_nps as _calc_nps

    rows = []
    today = datetime.today()
    # Determine last 3 complete ISO weeks
    current_iso = today.isocalendar()
    for delta_w in range(1, 4):  # 1=last week, 2=two weeks ago, 3=three weeks ago
        target_date = today - timedelta(weeks=delta_w)
        iso = target_date.isocalendar()
        t_jaar = int(iso[0])
        t_week = int(iso[1])

        # Overlap filter
        try:
            w_start = datetime.fromisocalendar(t_jaar, t_week, 1)
            w_end = w_start + timedelta(days=6)
        except (ValueError, TypeError):
            continue

        has_dates = df_loaded["aankomst"].notna() & df_loaded["vertrek"].notna()
        overlap = has_dates & (df_loaded["aankomst"] <= w_end) & (df_loaded["vertrek"] >= w_start)
        fallback = ~has_dates & (df_loaded["vertrek_jaar"] == t_jaar) & (df_loaded["vertrek_week"] == t_week)
        week_df = df_loaded[overlap | fallback]

        # Per segment
        segs = week_df["segment"].dropna().unique().tolist() or ["(alle)"]
        for seg in sorted(segs):
            seg_df = week_df[week_df["segment"] == seg] if seg != "(alle)" else week_df
            scored_df = seg_df[seg_df["score"].notna()]
            n_resp = int(scored_df["reserveringsnummer"].nunique()) if "reserveringsnummer" in scored_df.columns else len(scored_df)
            alg_df = scored_df[scored_df["vraag_label"] == "Algemeen oordeel"]
            nps_res = _calc_nps(alg_df, min_responses=1)
            nps_str = f"{nps_res['nps']:+.1f}" if nps_res else "n.v.t."
            rows.append({
                "Week": t_week,
                "Jaar": t_jaar,
                "Periode": f"{w_start.strftime('%d-%m')} t/m {w_end.strftime('%d-%m')}",
                "Segment": seg,
                "Respondenten": n_resp,
                "NPS Algemeen": nps_str,
            })

    return rows


# ============================================================
# Auto-ingest: load CSVs if DB is empty OR if CSV is newer than DB
# ============================================================
def auto_ingest_if_needed():
    camping_path = os.path.join(DATA_DIR, "camping.csv")
    accom_path = os.path.join(DATA_DIR, "accommodaties.csv")

    if not os.path.exists(camping_path) or not os.path.exists(accom_path):
        return  # No CSVs available, nothing to do

    df = load_data()

    # Check if DB needs refresh: empty, or CSV file is newer than DB file
    db_mtime = os.path.getmtime(DB_PATH) if os.path.exists(DB_PATH) else 0
    csv_mtime = max(os.path.getmtime(camping_path), os.path.getmtime(accom_path))
    needs_refresh = df.empty or (csv_mtime > db_mtime)

    if needs_refresh:
        with st.spinner("Data wordt geladen vanuit CSV bestanden..."):
            ingest_csv(camping_path, "Camping", "full_refresh")
            ingest_csv(accom_path, "Accommodaties", "full_refresh")
            refresh_data()
        st.success("Data bijgewerkt!")
        st.rerun()


auto_ingest_if_needed()

# Load data
df = load_data()


# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    if os.path.exists(LOGO_WIT):
        st.image(LOGO_WIT, width=180)
    st.markdown("### Guest Insights")
    st.markdown("---")

    page = st.radio(
        "Navigatie",
        [
            "Dashboard",
            "Weekrapport",
            "Thema Analyse",
            "Woordenwolk & Trends",
            "Leaderboards",
            "Accommodatie Deep Dive",
            "Data Bijwerken",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")

    # Global filters
    if not df.empty:
        st.markdown("#### Filters")

        # Period filter (based on vertrek/departure week)
        jaren = sorted(df["vertrek_jaar"].dropna().unique())
        if jaren:
            selected_jaren = st.multiselect("Jaar", jaren, default=jaren[-1:] if jaren else [])
        else:
            selected_jaren = []

        # Segment
        segmenten = sorted(df["segment"].dropna().unique())
        selected_segment = st.multiselect("Segment", segmenten, default=segmenten)

        # Objectsoort
        objectsoorten = sorted(df["objectsoort"].dropna().unique())
        selected_objectsoort = st.multiselect("Objectsoort", objectsoorten, default=[])

        # Objectnaam
        if selected_objectsoort:
            objectnamen = sorted(
                df[df["objectsoort"].isin(selected_objectsoort)]["objectnaam"].dropna().unique()
            )
        else:
            objectnamen = sorted(df["objectnaam"].dropna().unique())
        selected_objectnaam = st.multiselect("Objectnaam", objectnamen, default=[])
    else:
        selected_jaren = []
        selected_segment = []
        selected_objectsoort = []
        selected_objectnaam = []



# ============================================================
# Apply filters
# ============================================================
def apply_filters(data):
    filtered = data.copy()
    if selected_jaren:
        filtered = filtered[filtered["vertrek_jaar"].isin(selected_jaren)]
    if selected_segment:
        filtered = filtered[filtered["segment"].isin(selected_segment)]
    if selected_objectsoort:
        filtered = filtered[filtered["objectsoort"].isin(selected_objectsoort)]
    if selected_objectnaam:
        filtered = filtered[filtered["objectnaam"].isin(selected_objectnaam)]
    return filtered


fdf = apply_filters(df) if not df.empty else df

# Plotly layout defaults
PLOTLY_LAYOUT = dict(
    font=dict(family="Inter, Helvetica, sans-serif", color=COLORS["tekst_donker"]),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=20, r=20, t=40, b=20),
)


# ============================================================
# PAGE: Dashboard
# ============================================================
if page == "Dashboard":
    st.title("Dashboard")

    if fdf.empty:
        st.warning("Geen data beschikbaar. Ga naar 'Data Bijwerken' om CSV's te laden.")
        st.stop()

    # KPI row
    scored = fdf[fdf["score"].notna()]
    col1, col2, col3, col4, col5 = st.columns(5)

    overall = calc_nps(scored[scored["vraag_label"] == "Algemeen oordeel"])
    with col1:
        st.metric("Overall NPS", f"{overall['nps']:+.0f}" if overall else "-",
                   help="Gebaseerd op 'Algemeen oordeel' vraag")

    for col_widget, cat_name in [
        (col2, "Schoonmaak"),
        (col3, "Verblijf"),
        (col4, "Prijs/Kwaliteit"),
    ]:
        cat_data = scored[scored["categorie"] == cat_name]
        result = calc_nps(cat_data)
        with col_widget:
            st.metric(f"{cat_name} NPS",
                      f"{result['nps']:+.0f}" if result else "-")

    with col5:
        st.metric("Responses", f"{len(scored):,}")

    st.markdown("---")

    # Charts row
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("NPS Trend per Week")
        trend = nps_trend(scored, "week")
        if not trend.empty:
            fig = px.line(
                trend, x="datum", y="nps",
                color_discrete_sequence=[COLORS["diep_bosgroen"]],
                labels={"datum": "", "nps": "NPS"},
            )
            fig.update_layout(**PLOTLY_LAYOUT)
            fig.update_traces(line=dict(width=3))
            fig.add_hline(y=0, line_dash="dash", line_color=COLORS["tekst_licht"], opacity=0.5)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Onvoldoende data voor trendweergave.")

    with chart_col2:
        st.subheader("Response Volume per Week")
        if not trend.empty:
            fig = px.bar(
                trend, x="datum", y="n",
                color_discrete_sequence=[COLORS["zandgroen"]],
                labels={"datum": "", "n": "Aantal"},
            )
            fig.update_layout(**PLOTLY_LAYOUT)
            fig.update_traces(marker=dict(cornerradius=4))
            st.plotly_chart(fig, width="stretch")

    st.markdown("---")

    # NPS per vraag (all individual questions)
    st.subheader("NPS per Vraag")
    # Filter out "Vrije review" which has no scores
    scored_questions = scored[scored["vraag_label"] != "Vrije review"]
    vraag_nps = nps_by_group(scored_questions, "vraag_label", min_responses=5)
    if not vraag_nps.empty:
        vraag_nps = vraag_nps.sort_values("nps", ascending=True)
        fig = px.bar(
            vraag_nps, x="nps", y="vraag_label", orientation="h",
            text="nps",
            color_discrete_sequence=[COLORS["diep_bosgroen"]],
            labels={"nps": "NPS", "vraag_label": ""},
        )
        fig.update_layout(**PLOTLY_LAYOUT, height=max(300, len(vraag_nps) * 40))
        fig.update_traces(texttemplate="%{text:+.0f}", textposition="outside",
                          marker=dict(cornerradius=4))
        st.plotly_chart(fig, width="stretch")

    st.markdown("---")

    # Leaderboards per objectsoort
    lb_col1, lb_col2 = st.columns(2)

    with lb_col1:
        st.subheader("Top 10 Best Scorend")
        top = leaderboard(scored, "objectsoort", min_responses=5, top_n=10, ascending=False)
        if not top.empty:
            fig = px.bar(
                top.sort_values("nps"), x="nps", y="objectsoort", orientation="h",
                text="nps",
                color_discrete_sequence=[COLORS["diep_bosgroen"]],
                labels={"nps": "NPS", "objectsoort": ""},
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=400)
            fig.update_traces(texttemplate="%{text:+.0f}", textposition="outside",
                              marker=dict(cornerradius=4))
            st.plotly_chart(fig, width="stretch")

    with lb_col2:
        st.subheader("Top 10 Slechtst Scorend")
        bottom = leaderboard(scored, "objectsoort", min_responses=5, top_n=10, ascending=True)
        if not bottom.empty:
            fig = px.bar(
                bottom.sort_values("nps", ascending=False), x="nps", y="objectsoort",
                orientation="h", text="nps",
                color_discrete_sequence=[COLORS["heide_paars"]],
                labels={"nps": "NPS", "objectsoort": ""},
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=400)
            fig.update_traces(texttemplate="%{text:+.0f}", textposition="outside",
                              marker=dict(cornerradius=4))
            st.plotly_chart(fig, width="stretch")


# ============================================================
# PAGE: Weekrapport
# ============================================================
elif page == "Weekrapport":
    st.title("Weekrapport Generator")

    if df.empty:
        st.warning("Geen data beschikbaar.")
        st.stop()

    rc1, rc2 = st.columns(2)
    with rc1:
        jaren_all = sorted(df["vertrek_jaar"].dropna().unique())
        rapport_jaar = st.selectbox("Jaar", jaren_all,
                                    index=len(jaren_all) - 1 if jaren_all else 0)
    with rc2:
        weken = sorted(df[df["vertrek_jaar"] == rapport_jaar]["vertrek_week"].dropna().unique())
        rapport_week = st.selectbox("Week", weken,
                                    index=len(weken) - 1 if weken else 0)

    if st.button("Genereer Rapport"):
        with st.spinner("Rapport wordt gegenereerd..."):
            html = generate_html_report(df, rapport_jaar, rapport_week)

            # Store in session state for persistence
            st.session_state["weekrapport_html"] = html
            st.session_state["weekrapport_jaar"] = rapport_jaar
            st.session_state["weekrapport_week"] = rapport_week

    # Show report if generated
    if "weekrapport_html" in st.session_state:
        html = st.session_state["weekrapport_html"]
        r_jaar = st.session_state["weekrapport_jaar"]
        r_week = st.session_state["weekrapport_week"]

        # Render HTML preview using Streamlit components
        import streamlit.components.v1 as components
        components.html(html, height=800, scrolling=True)

        st.markdown("---")

        # HTML download
        st.download_button(
            "⬇️ Download HTML Rapport",
            html.encode("utf-8"),
            file_name=f"MT_Rapport_Week_{r_week}_{r_jaar}.html",
            mime="text/html",
        )


# ============================================================
# PAGE: Thema Analyse
# ============================================================
elif page == "Thema Analyse":
    st.title("Thema Analyse")

    if fdf.empty:
        st.warning("Geen data beschikbaar.")
        st.stop()

    zoekterm = st.text_input(
        "Zoek op thema",
        placeholder="bijv. jacuzzi, schoonmaak, wifi, geluid, bedden...",
    )

    if zoekterm:
        zoekterm_lower = zoekterm.lower()

        # Search in aanvulling and antwoord (text)
        mask = (
            fdf["aanvulling"].str.lower().str.contains(zoekterm_lower, na=False) |
            fdf["antwoord"].astype(str).str.lower().str.contains(zoekterm_lower, na=False)
        )
        results = fdf[mask].copy()

        st.markdown(f"### Resultaten voor '{zoekterm}'")

        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Aantal meldingen", len(results))
        with m2:
            scores = results["score"].dropna()
            st.metric("Gem. score", f"{scores.mean():.1f}" if len(scores) > 0 else "-")
        with m3:
            nps_result = calc_nps(results)
            st.metric("NPS", f"{nps_result['nps']:+.0f}" if nps_result else "-")

        st.markdown("---")

        # Trend over time
        if not results.empty and results["vertrek_jaar"].notna().any():
            st.subheader("Trend over Tijd")
            theme_trend = nps_trend(results[results["score"].notna()], "maand")
            if not theme_trend.empty:
                fig = px.line(
                    theme_trend, x="datum", y="n",
                    color_discrete_sequence=[COLORS["diep_bosgroen"]],
                    labels={"datum": "", "n": "Aantal meldingen"},
                )
                fig.update_layout(**PLOTLY_LAYOUT)
                st.plotly_chart(fig, width="stretch")

        # Involved accommodations
        st.subheader("Betrokken Accommodaties")
        obj_counts = results.groupby("objectnaam").size().sort_values(ascending=False).head(20)
        if not obj_counts.empty:
            fig = px.bar(
                x=obj_counts.values, y=obj_counts.index,
                orientation="h",
                color_discrete_sequence=[COLORS["zandgroen"]],
                labels={"x": "Aantal", "y": ""},
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=max(300, len(obj_counts) * 25))
            fig.update_traces(marker=dict(cornerradius=4))
            st.plotly_chart(fig, width="stretch")

        # Show review texts
        st.subheader("Reviews")
        review_texts_list = []
        for _, row in results.head(20).iterrows():
            tekst = row.get("aanvulling", "")
            if not tekst or str(tekst).strip() == "" or str(tekst).strip().lower() == "nan":
                tekst = str(row.get("antwoord", ""))
            score = row.get("score")
            score_str = f"Score: {int(score)}" if pd.notna(score) else ""
            obj = row.get("objectnaam", "")
            datum = row.get("ingevuld_op", "")

            review_texts_list.append({
                "tekst": str(tekst).strip(),
                "score": score,
                "objectnaam": str(obj),
                "datum": str(datum),
            })

            with st.expander(f"{score_str} | {obj} | {datum}"):
                st.write(tekst)

        # PDF export
        st.markdown("---")
        st.subheader("Exporteer Analyse")
        pdf_bytes = generate_theme_pdf(
            zoekterm=zoekterm,
            results_df=results,
            nps_result=nps_result,
            theme_trend_data=None,
            obj_counts=obj_counts,
            review_texts=review_texts_list,
        )
        st.download_button(
            "📄 Download PDF Rapport",
            pdf_bytes,
            file_name=f"thema_analyse_{zoekterm}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            key="theme_pdf_download",
        )


# ============================================================
# PAGE: Woordenwolk & Trends
# ============================================================
elif page == "Woordenwolk & Trends":
    st.title("Woordenwolk & Sentimenttrends")

    if fdf.empty:
        st.warning("Geen data beschikbaar.")
        st.stop()

    # Filter to rows with actual text
    has_text_mask = (
        fdf["aanvulling"].notna() &
        (fdf["aanvulling"].astype(str).str.strip() != "") &
        (fdf["aanvulling"].astype(str).str.strip().str.lower() != "nan")
    )
    text_data = fdf[has_text_mask].copy()

    if len(text_data) < 10:
        st.info("Onvoldoende reviews met tekst voor analyse (minimaal 10 nodig).")
        st.stop()

    # Split by sentiment using score as proxy
    df_positive = text_data[text_data["score"] >= 8]
    df_negative = text_data[text_data["score"] <= 6]

    # --- KPI strip ---
    kpi1, kpi2, kpi3 = st.columns(3)
    with kpi1:
        st.metric("Reviews met tekst", f"{len(text_data):,}")
    with kpi2:
        pct_pos = len(df_positive) / len(text_data) * 100 if len(text_data) > 0 else 0
        st.metric("Positief sentiment", f"{pct_pos:.0f}%",
                  help="Aandeel reviews met score \u2265 8")
    with kpi3:
        pct_neg = len(df_negative) / len(text_data) * 100 if len(text_data) > 0 else 0
        st.metric("Negatief sentiment", f"{pct_neg:.0f}%",
                  help="Aandeel reviews met score \u2264 6")

    st.markdown("---")

    # --- Signalen (alerts) bovenaan ---
    alerts = compute_aspect_alerts(text_data)
    if alerts:
        spikes = [a for a in alerts if a["alert_type"] == "spike"]
        improvements = [a for a in alerts if a["alert_type"] == "improvement"]

        if spikes:
            for a in spikes[:3]:
                st.markdown(
                    f'<div style="background:#FDF0F0; border-left:4px solid {COLORS["heide_paars"]}; '
                    f'border-radius:0 8px 8px 0; padding:12px 18px; margin-bottom:8px;">'
                    f'<strong style="color:{COLORS["heide_paars"]};">\u26a0\ufe0f Aandachtspunt:</strong> '
                    f'<span style="color:{COLORS["tekst_donker"]};">'
                    f'<strong>{a["aspect"]}</strong> heeft {a["recent_count"]} klachten in {a["recent_period"]} '
                    f'(normaal {a["baseline_avg"]:.0f}/maand, <strong>{a["change_pct"]:+.0f}%</strong>)</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        if improvements:
            for a in improvements[:3]:
                st.markdown(
                    f'<div style="background:#F0F7F0; border-left:4px solid {COLORS["diep_bosgroen"]}; '
                    f'border-radius:0 8px 8px 0; padding:12px 18px; margin-bottom:8px;">'
                    f'<strong style="color:{COLORS["diep_bosgroen"]};">\u2705 Verbetering:</strong> '
                    f'<span style="color:{COLORS["tekst_donker"]};">'
                    f'<strong>{a["aspect"]}</strong> is gedaald naar {a["recent_count"]} klachten in {a["recent_period"]} '
                    f'(was {a["baseline_avg"]:.0f}/maand, <strong>{a["change_pct"]:+.0f}%</strong>)</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("---")

    # --- Word clouds ---
    wc_col1, wc_col2 = st.columns(2)

    with wc_col1:
        st.markdown(
            f'<h3 style="color:{COLORS["diep_bosgroen"]};">Wat gasten waarderen</h3>',
            unsafe_allow_html=True,
        )
        if len(df_positive) >= 3:
            pos_terms = extract_tfidf_terms(df_positive["aanvulling"].tolist(), top_n=40)
            pos_img = generate_wordcloud_image(pos_terms, "positive")
            if pos_img:
                st.image(pos_img, width="stretch")
                top5_pos = list(pos_terms.keys())[:5]
                st.markdown(
                    f'<div style="background:{COLORS["licht_beige"]}; padding:10px 16px; '
                    f'border-radius:8px; font-size:14px; color:{COLORS["tekst_donker"]};">'
                    f'<strong>Top 5:</strong> {", ".join(top5_pos)}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.info("Onvoldoende data voor positieve woordenwolk.")
        else:
            st.info("Te weinig positieve reviews voor analyse.")

    with wc_col2:
        st.markdown(
            f'<h3 style="color:{COLORS["heide_paars"]};">Waar gasten over klagen</h3>',
            unsafe_allow_html=True,
        )
        if len(df_negative) >= 3:
            neg_terms = extract_tfidf_terms(df_negative["aanvulling"].tolist(), top_n=40)
            neg_img = generate_wordcloud_image(neg_terms, "negative")
            if neg_img:
                st.image(neg_img, width="stretch")
                top5_neg = list(neg_terms.keys())[:5]
                st.markdown(
                    f'<div style="background:#F9F0F7; padding:10px 16px; '
                    f'border-radius:8px; font-size:14px; color:{COLORS["tekst_donker"]};">'
                    f'<strong>Top 5:</strong> {", ".join(top5_neg)}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.info("Onvoldoende data voor negatieve woordenwolk.")
        else:
            st.info("Te weinig negatieve reviews voor analyse.")

    st.markdown("---")

    # --- Aspect Sentiment Analysis ---
    st.subheader("Sentiment per Aspect")
    st.markdown(
        f'<p style="color:{COLORS["tekst_licht"]}; font-size:14px; margin-top:-8px;">'
        f'Hoe gasten denken over specifieke onderdelen van hun verblijf. '
        f'Gesorteerd op meest negatief = meest aandacht nodig.</p>',
        unsafe_allow_html=True,
    )

    # --- Segment tabs: Totaal / Accommodaties / Camping ---
    # For the segment tabs we ignore the sidebar segment-filter so both
    # Accommodaties and Camping are always available as tabs.
    # Other filters (jaar, objectsoort, objectnaam) are still applied.
    all_segments_data = df.copy()
    if selected_jaren:
        all_segments_data = all_segments_data[all_segments_data["vertrek_jaar"].isin(selected_jaren)]
    if selected_objectsoort:
        all_segments_data = all_segments_data[all_segments_data["objectsoort"].isin(selected_objectsoort)]
    if selected_objectnaam:
        all_segments_data = all_segments_data[all_segments_data["objectnaam"].isin(selected_objectnaam)]
    # Filter to rows with text
    all_seg_text_mask = (
        all_segments_data["aanvulling"].notna() &
        (all_segments_data["aanvulling"].astype(str).str.strip() != "") &
        (all_segments_data["aanvulling"].astype(str).str.strip().str.lower() != "nan")
    )
    all_segments_text = all_segments_data[all_seg_text_mask].copy()

    available_segments = all_segments_text["segment"].dropna().unique().tolist()
    tab_labels = ["Totaal"]
    if "Accommodaties" in available_segments:
        tab_labels.append("Accommodaties")
    if "Camping" in available_segments:
        tab_labels.append("Camping")

    segment_tabs = st.tabs(tab_labels)

    # Pre-compute sentiment for the full dataset (populates the BERT cache)
    aspect_df_total = compute_aspect_sentiment(all_segments_text)

    for tab_idx, tab_label in enumerate(tab_labels):
        with segment_tabs[tab_idx]:
            # Filter data per tab
            if tab_label == "Totaal":
                tab_data = all_segments_text
                aspect_df = aspect_df_total
            else:
                tab_data = all_segments_text[all_segments_text["segment"] == tab_label]
                if len(tab_data) < 10:
                    st.info(f"Onvoldoende reviews voor {tab_label} (minimaal 10 nodig).")
                    continue
                aspect_df = compute_aspect_sentiment(tab_data)

            if aspect_df.empty:
                st.info("Geen aspectdata beschikbaar voor dit segment.")
                continue

            # Stacked horizontal bar chart: positive vs negative per aspect
            fig = go.Figure()

            # Reverse order so most-negative is on top visually
            plot_df = aspect_df.sort_values("pct_negatief", ascending=True)

            # Aspect labels with mention count
            y_labels = [
                f'{a} ({t})'
                for a, t in zip(plot_df["aspect"], plot_df["totaal"])
            ]

            fig.add_trace(go.Bar(
                y=y_labels,
                x=plot_df["pct_positief"],
                name="Positief",
                orientation="h",
                marker=dict(color=COLORS["diep_bosgroen"], cornerradius=4),
                text=[f'{v:.0f}%' for v in plot_df["pct_positief"]],
                textposition="inside",
                textfont=dict(color="white", size=12),
            ))
            fig.add_trace(go.Bar(
                y=y_labels,
                x=[100 - row["pct_positief"] - row["pct_negatief"] for _, row in plot_df.iterrows()],
                name="Neutraal",
                orientation="h",
                marker=dict(color=COLORS["natuurlijk_beige"], cornerradius=4),
                textposition="none",
            ))
            fig.add_trace(go.Bar(
                y=y_labels,
                x=plot_df["pct_negatief"],
                name="Negatief",
                orientation="h",
                marker=dict(color=COLORS["heide_paars"], cornerradius=4),
                text=[f'{v:.0f}%' for v in plot_df["pct_negatief"]],
                textposition="inside",
                textfont=dict(color="white", size=12),
            ))

            fig.update_layout(
                **PLOTLY_LAYOUT,
                barmode="stack",
                height=max(400, len(plot_df) * 44),
                xaxis=dict(title="", showticklabels=False, showgrid=False),
                yaxis=dict(title="", tickfont=dict(size=12)),
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02,
                    xanchor="center", x=0.5, font=dict(size=12),
                ),
            )
            st.plotly_chart(fig, width="stretch", key=f"aspect_chart_{tab_label}")

            # --- Export knop ---
            csv_export = aspect_df[["aspect", "positief", "negatief", "neutraal", "totaal", "pct_positief", "pct_negatief", "sentiment_score"]].copy()
            csv_export.columns = ["Aspect", "Positief", "Negatief", "Neutraal", "Totaal", "% Positief", "% Negatief", "Sentiment Score"]
            st.download_button(
                f"📥 Exporteer aspect-data als CSV ({tab_label})",
                csv_export.to_csv(index=False, sep=";").encode("utf-8-sig"),
                file_name=f"aspect_sentiment_{tab_label.lower()}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                key=f"csv_export_{tab_label}",
            )

            st.markdown("---")

            # --- Detail per aspect: YoY + quotes ---
            st.subheader("Detail per Aspect")
            st.markdown(
                f'<p style="color:{COLORS["tekst_licht"]}; font-size:14px; margin-top:-8px;">'
                f'Klik op een aspect voor jaar-op-jaar vergelijking en representatieve gastcitaten.</p>',
                unsafe_allow_html=True,
            )

            # Filter for YoY based on segment (use all_segments_data to bypass segment filter)
            if tab_label == "Totaal":
                fdf_segment = all_segments_data
            else:
                fdf_segment = all_segments_data[all_segments_data["segment"] == tab_label]

            for _, row in aspect_df.iterrows():
                aspect_name = row["aspect"]
                totaal = int(row["totaal"])
                pct_neg = row["pct_negatief"]
                pct_pos = row["pct_positief"]
                sent_score = row["sentiment_score"]

                with st.expander(f"{aspect_name}  —  {totaal} mentions  |  {pct_pos:.0f}% positief  |  {pct_neg:.0f}% negatief"):
                    # YoY comparison
                    yoy = compute_aspect_yoy(fdf_segment, aspect_name)
                    if yoy:
                        delta = yoy["delta"]
                        if delta > 2:
                            trend_icon = "\u2b06\ufe0f"
                            trend_text = f"meer klachten ({yoy['delta']:+.1f}pp)"
                            trend_color = COLORS["heide_paars"]
                        elif delta < -2:
                            trend_icon = "\u2b07\ufe0f"
                            trend_text = f"minder klachten ({yoy['delta']:+.1f}pp)"
                            trend_color = COLORS["diep_bosgroen"]
                        else:
                            trend_icon = "\u2796"
                            trend_text = "stabiel"
                            trend_color = COLORS["tekst_licht"]

                        st.markdown(
                            f'<div style="background:{COLORS["licht_beige"]}; padding:12px 16px; '
                            f'border-radius:8px; margin-bottom:12px;">'
                            f'<strong>Jaar-op-jaar:</strong> '
                            f'{yoy["prev_jaar"]}: {yoy["prev_pct_neg"]:.1f}% negatief \u2192 '
                            f'{yoy["curr_jaar"]}: {yoy["curr_pct_neg"]:.1f}% negatief '
                            f'<span style="color:{trend_color}; font-weight:600;">{trend_icon} {trend_text}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                    # Quotes in two columns – use tab_data for segment-specific quotes
                    q_col1, q_col2 = st.columns(2)

                    with q_col1:
                        st.markdown(f'**Negatieve citaten:**')
                        neg_quotes = get_aspect_quotes(tab_data, aspect_name, "negative", 3)
                        if neg_quotes:
                            for q in neg_quotes:
                                tekst = q["tekst"].encode("ascii", "replace").decode("ascii")
                                st.markdown(
                                    f'<div style="background:#FDF0F0; border-left:3px solid {COLORS["heide_paars"]}; '
                                    f'padding:10px 14px; margin-bottom:8px; border-radius:0 6px 6px 0; font-size:13px;">'
                                    f'<div style="color:{COLORS["tekst_licht"]}; font-size:11px; margin-bottom:4px;">'
                                    f'Score {q["score"]} | {q["objectnaam"]} | {q["datum"]}</div>'
                                    f'{tekst}</div>',
                                    unsafe_allow_html=True,
                                )
                        else:
                            st.markdown(f'*Geen negatieve citaten gevonden.*')

                    with q_col2:
                        st.markdown(f'**Positieve citaten:**')
                        pos_quotes = get_aspect_quotes(tab_data, aspect_name, "positive", 3)
                        if pos_quotes:
                            for q in pos_quotes:
                                tekst = q["tekst"].encode("ascii", "replace").decode("ascii")
                                st.markdown(
                                    f'<div style="background:#F0F7F0; border-left:3px solid {COLORS["diep_bosgroen"]}; '
                                    f'padding:10px 14px; margin-bottom:8px; border-radius:0 6px 6px 0; font-size:13px;">'
                                    f'<div style="color:{COLORS["tekst_licht"]}; font-size:11px; margin-bottom:4px;">'
                                    f'Score {q["score"]} | {q["objectnaam"]} | {q["datum"]}</div>'
                                    f'{tekst}</div>',
                                    unsafe_allow_html=True,
                                )
                        else:
                            st.markdown(f'*Geen positieve citaten gevonden.*')


# ============================================================
# PAGE: Leaderboards
# ============================================================
elif page == "Leaderboards":
    st.title("Leaderboards")

    if fdf.empty:
        st.warning("Geen data beschikbaar.")
        st.stop()

    scored = fdf[fdf["score"].notna()]

    min_resp = st.slider("Minimum aantal responses", 1, 50, 5)

    tab1, tab2 = st.tabs(["Per Objectnaam", "Per Objectsoort"])

    with tab1:
        st.subheader("Ranking per Accommodatie / Kampeerplaats")
        ranking = nps_by_group(scored, "objectnaam", min_responses=min_resp)
        if not ranking.empty:
            ranking = ranking.sort_values("nps", ascending=False).reset_index(drop=True)
            ranking.index = ranking.index + 1
            ranking.index.name = "Rank"
            st.dataframe(
                ranking[["objectnaam", "nps", "avg_score", "n",
                         "pct_promoters", "pct_detractors"]].rename(columns={
                    "objectnaam": "Naam", "nps": "NPS", "avg_score": "Gem.",
                    "n": "Responses", "pct_promoters": "% Promoters",
                    "pct_detractors": "% Detractors",
                }),
                width="stretch",
                height=600,
            )

    with tab2:
        st.subheader("Ranking per Objectsoort")
        ranking_type = nps_by_group(scored, "objectsoort", min_responses=min_resp)
        if not ranking_type.empty:
            ranking_type = ranking_type.sort_values("nps", ascending=False)
            fig = px.bar(
                ranking_type, x="objectsoort", y="nps", text="nps",
                color="nps",
                color_continuous_scale=[COLORS["heide_paars"], COLORS["natuurlijk_beige"],
                                        COLORS["diep_bosgroen"]],
                labels={"objectsoort": "", "nps": "NPS"},
            )
            fig.update_layout(**PLOTLY_LAYOUT, height=500, showlegend=False)
            fig.update_traces(texttemplate="%{text:+.0f}", textposition="outside",
                              marker=dict(cornerradius=4))
            st.plotly_chart(fig, width="stretch")

            st.dataframe(
                ranking_type[["objectsoort", "nps", "avg_score", "n"]].rename(columns={
                    "objectsoort": "Type", "nps": "NPS", "avg_score": "Gem.",
                    "n": "Responses",
                }),
                width="stretch",
            )


# ============================================================
# PAGE: Accommodatie Deep Dive
# ============================================================
elif page == "Accommodatie Deep Dive":
    st.title("Accommodatie Deep Dive")

    if fdf.empty:
        st.warning("Geen data beschikbaar.")
        st.stop()

    # Select objectsoort first, then objectnaam
    dd_soort = st.selectbox(
        "Selecteer type accommodatie",
        sorted(df["objectsoort"].dropna().unique()),
    )

    soort_data = df[df["objectsoort"] == dd_soort]
    scored_soort = soort_data[soort_data["score"].notna()]

    if scored_soort.empty:
        st.info("Geen data voor dit type.")
        st.stop()

    # Overall stats for this type
    m1, m2, m3 = st.columns(3)
    type_nps = calc_nps(scored_soort)
    with m1:
        st.metric("NPS", f"{type_nps['nps']:+.0f}" if type_nps else "-")
    with m2:
        st.metric("Gem. Score", f"{type_nps['avg_score']:.1f}" if type_nps else "-")
    with m3:
        st.metric("Responses", type_nps["n"] if type_nps else 0)

    st.markdown("---")

    # Trend per year
    st.subheader("Trend door de Jaren")
    year_trend = nps_by_group(scored_soort, "vertrek_jaar", min_responses=5)
    if not year_trend.empty:
        year_trend = year_trend.sort_values("vertrek_jaar")
        fig = px.line(
            year_trend, x="vertrek_jaar", y="nps",
            color_discrete_sequence=[COLORS["diep_bosgroen"]],
            markers=True,
            labels={"vertrek_jaar": "Jaar", "nps": "NPS"},
        )
        fig.update_layout(**PLOTLY_LAYOUT)
        fig.add_hline(y=0, line_dash="dash", line_color=COLORS["tekst_licht"], opacity=0.5)
        st.plotly_chart(fig, width="stretch")

    # NPS per vraag for this type
    st.subheader("NPS per Vraag")
    scored_questions = scored_soort[scored_soort["vraag_label"] != "Vrije review"]
    vraag_nps = nps_by_group(scored_questions, "vraag_label", min_responses=3)
    if not vraag_nps.empty:
        vraag_nps = vraag_nps.sort_values("nps", ascending=True)
        fig = px.bar(
            vraag_nps, x="nps", y="vraag_label", orientation="h",
            text="nps",
            color_discrete_sequence=[COLORS["diep_bosgroen"]],
            labels={"nps": "NPS", "vraag_label": ""},
        )
        fig.update_layout(**PLOTLY_LAYOUT, height=max(300, len(vraag_nps) * 40))
        fig.update_traces(texttemplate="%{text:+.0f}", textposition="outside",
                          marker=dict(cornerradius=4))
        st.plotly_chart(fig, width="stretch")

    # Comparison between units
    st.subheader("Vergelijking tussen Units")
    unit_nps = nps_by_group(scored_soort, "objectnaam", min_responses=3)
    if not unit_nps.empty:
        unit_nps = unit_nps.sort_values("nps", ascending=False)
        fig = px.bar(
            unit_nps.head(30), x="nps", y="objectnaam", orientation="h",
            text="nps",
            color="nps",
            color_continuous_scale=[COLORS["heide_paars"], COLORS["natuurlijk_beige"],
                                    COLORS["diep_bosgroen"]],
            labels={"nps": "NPS", "objectnaam": ""},
        )
        fig.update_layout(**PLOTLY_LAYOUT, height=max(300, len(unit_nps.head(30)) * 22),
                          showlegend=False)
        fig.update_traces(texttemplate="%{text:+.0f}", textposition="outside",
                          marker=dict(cornerradius=4))
        st.plotly_chart(fig, width="stretch")

    # Top complaints
    st.subheader("Belangrijkste Klachten")
    # Filter: score <=6, aanvulling must contain real text
    klachten_mask = (
        (soort_data["score"].notna()) &
        (soort_data["score"] <= 6) &
        (soort_data["aanvulling"].notna()) &
        (soort_data["aanvulling"].astype(str).str.strip() != "") &
        (soort_data["aanvulling"].astype(str).str.strip().str.lower() != "nan")
    )
    complaints = soort_data[klachten_mask].sort_values("score").head(10)

    if complaints.empty:
        st.info("Geen klachten met toelichting gevonden.")
    else:
        for _, row in complaints.iterrows():
            score = int(row["score"]) if pd.notna(row["score"]) else "?"
            obj = str(row.get("objectnaam", "")).strip()
            # Clean text: replace problematic characters
            tekst = str(row["aanvulling"]).strip()[:300]
            tekst = tekst.encode("ascii", "replace").decode("ascii")
            if tekst and tekst.lower() != "nan":
                score_color = COLORS["heide_paars"] if score <= 4 else COLORS["zandgroen"]
                st.markdown(
                    f'<div style="background:#F9F7F4; border-left:4px solid {score_color}; '
                    f'border-radius:0 8px 8px 0; padding:14px 18px; margin-bottom:10px;">'
                    f'<div style="display:flex; justify-content:space-between; margin-bottom:6px;">'
                    f'<strong style="color:{COLORS["diep_bosgroen"]};">{obj}</strong>'
                    f'<span style="background:{score_color}; color:white; padding:2px 10px; '
                    f'border-radius:12px; font-size:13px; font-weight:600;">Score {score}</span>'
                    f'</div>'
                    f'<div style="color:{COLORS["tekst_donker"]}; font-size:14px; line-height:1.6;">{tekst}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # AI-style summary
    st.subheader("Samenvatting & Aanbevelingen")
    if type_nps:
        # Generate a data-driven summary
        top_vraag = vraag_nps.sort_values("nps", ascending=False).head(1) if not vraag_nps.empty else pd.DataFrame()
        bottom_vraag = vraag_nps.sort_values("nps", ascending=True).head(1) if not vraag_nps.empty else pd.DataFrame()

        summary_parts = [f"**{dd_soort}** heeft een overall NPS van **{type_nps['nps']:+.0f}** "
                         f"op basis van **{type_nps['n']}** responses."]

        if not top_vraag.empty:
            summary_parts.append(
                f"Sterkste vraag: **{top_vraag.iloc[0]['vraag_label']}** "
                f"(NPS {top_vraag.iloc[0]['nps']:+.0f})."
            )
        if not bottom_vraag.empty:
            summary_parts.append(
                f"Zwakste vraag: **{bottom_vraag.iloc[0]['vraag_label']}** "
                f"(NPS {bottom_vraag.iloc[0]['nps']:+.0f}). "
                f"Dit is het belangrijkste verbeterpunt."
            )

        st.markdown("\n\n".join(summary_parts))


# ============================================================
# PAGE: Data Bijwerken
# ============================================================
elif page == "Data Bijwerken":
    st.title("Data Bijwerken")

    st.markdown(
        "Upload hier de meest recente exports. Beide bestanden worden verwerkt met **Full Refresh** "
        "(alle bestaande data voor dat segment wordt vervangen door de nieuwe upload). "
        "Upload je wekelijkse totaalexport van camping én accommodaties."
    )

    st.markdown("---")

    # ── Upload widgets ──────────────────────────────────────
    col_c, col_a = st.columns(2)
    with col_c:
        st.subheader("🏕️ Camping")
        camping_file = st.file_uploader(
            "Upload camping CSV",
            type=["csv"],
            key="camping_upload",
            help="Semicolon-gescheiden, latin-1 codering (export uit reserveringssysteem)",
        )
        if camping_file:
            c_ok, c_msg, c_rows = validate_csv_upload(camping_file.getvalue(), "Camping")
            if c_ok:
                st.success(f"✅ {c_msg}")
            else:
                st.error(f"❌ {c_msg}")

    with col_a:
        st.subheader("🏠 Accommodaties")
        accom_file = st.file_uploader(
            "Upload accommodaties CSV",
            type=["csv"],
            key="accom_upload",
            help="Semicolon-gescheiden, latin-1 codering (export uit reserveringssysteem)",
        )
        if accom_file:
            a_ok, a_msg, a_rows = validate_csv_upload(accom_file.getvalue(), "Accommodaties")
            if a_ok:
                st.success(f"✅ {a_msg}")
            else:
                st.error(f"❌ {a_msg}")

    st.markdown("---")

    # ── Single process button ────────────────────────────────
    both_valid = (
        camping_file is not None and validate_csv_upload(camping_file.getvalue(), "Camping")[0]
        and accom_file is not None and validate_csv_upload(accom_file.getvalue(), "Accommodaties")[0]
    )
    camping_only = camping_file is not None and validate_csv_upload(camping_file.getvalue(), "Camping")[0] if camping_file else False
    accom_only = accom_file is not None and validate_csv_upload(accom_file.getvalue(), "Accommodaties")[0] if accom_file else False

    any_valid = camping_only or accom_only

    if not any_valid:
        st.info("Upload minimaal één geldig CSV-bestand om door te gaan.")
    else:
        btn_label = "🔄 Verwerk uploads (Full Refresh)"
        if st.button(btn_label, type="primary", use_container_width=True):
            import tempfile
            results = {}

            with st.spinner("Data wordt verwerkt..."):
                # Process Camping
                if camping_file and camping_only:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                        tmp.write(camping_file.getvalue())
                        tmp_path = tmp.name
                    try:
                        stats_c = ingest_csv(tmp_path, "Camping", "full_refresh")
                        results["Camping"] = stats_c
                        # Persist to data/ so auto_ingest_if_needed picks it up on cloud reboot
                        dest_c = os.path.join(DATA_DIR, "camping.csv")
                        with open(dest_c, "wb") as f_out:
                            f_out.write(camping_file.getvalue())
                    finally:
                        os.unlink(tmp_path)

                # Process Accommodaties
                if accom_file and accom_only:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                        tmp.write(accom_file.getvalue())
                        tmp_path = tmp.name
                    try:
                        stats_a = ingest_csv(tmp_path, "Accommodaties", "full_refresh")
                        results["Accommodaties"] = stats_a
                        # Persist to data/
                        dest_a = os.path.join(DATA_DIR, "accommodaties.csv")
                        with open(dest_a, "wb") as f_out:
                            f_out.write(accom_file.getvalue())
                    finally:
                        os.unlink(tmp_path)

                refresh_data()

            # ── Result banners ───────────────────────────────
            st.markdown("### Resultaat")
            for seg_name, stats in results.items():
                inserted = stats.get("inserted", 0)
                updated = stats.get("updated", 0)
                skipped = stats.get("skipped", 0)
                errors = stats.get("error", 0)
                total_read = stats.get("read", 0)

                if errors == 0:
                    st.success(
                        f"✅ **{seg_name}** — {total_read:,} rijen gelezen | "
                        f"{inserted:,} nieuw ingevoegd | {updated:,} bijgewerkt | "
                        f"{skipped:,} overgeslagen"
                    )
                else:
                    st.warning(
                        f"⚠️ **{seg_name}** — {total_read:,} rijen gelezen | "
                        f"{inserted:,} nieuw | {updated:,} bijgewerkt | "
                        f"{skipped:,} overgeslagen | **{errors} fouten**"
                    )
                    if stats.get("details"):
                        with st.expander("Foutdetails"):
                            st.code(stats["details"])

            st.session_state["upload_done"] = True
            st.rerun()

    # ── Post-upload: data preview + week verification ────────
    if st.session_state.get("upload_done") or not df.empty:
        st.markdown("---")
        df_fresh = load_data()

        if not df_fresh.empty:
            # Data preview
            st.subheader("📊 Data preview")
            p1, p2, p3, p4 = st.columns(4)
            with p1:
                st.metric("Totaal responses", f"{len(df_fresh):,}")
            with p2:
                segs_in_db = df_fresh["segment"].dropna().unique()
                st.metric("Segmenten", len(segs_in_db))
            with p3:
                jaren_in_db = df_fresh["vertrek_jaar"].dropna().unique()
                if len(jaren_in_db):
                    st.metric("Periode", f"{int(min(jaren_in_db))} – {int(max(jaren_in_db))}")
                else:
                    st.metric("Periode", "–")
            with p4:
                latest_vertrek = df_fresh["vertrek"].dropna().max()
                if pd.notna(latest_vertrek):
                    try:
                        st.metric("Laatste vertrek", latest_vertrek.strftime("%d-%m-%Y"))
                    except Exception:
                        st.metric("Laatste vertrek", str(latest_vertrek)[:10])
                else:
                    st.metric("Laatste vertrek", "–")

            st.markdown("---")

            # Week verification table
            st.subheader("📅 Verificatie weekrapporten (laatste 3 weken)")
            st.markdown(
                "Controle of de weekrapportages de juiste aantallen tonen "
                "(gebruikt dezelfde overlap-logica als het weekrapport)."
            )
            with st.spinner("Weekdata wordt berekend..."):
                week_rows = build_week_verification_table(df_fresh)

            if week_rows:
                week_verify_df = pd.DataFrame(week_rows)
                st.dataframe(
                    week_verify_df.rename(columns={
                        "Week": "Week",
                        "Jaar": "Jaar",
                        "Periode": "Periode",
                        "Segment": "Segment",
                        "Respondenten": "# Respondenten",
                        "NPS Algemeen": "NPS Algemeen oordeel",
                    }),
                    hide_index=True,
                    width="stretch",
                )
                st.caption(
                    "Tip: genereer het weekrapport voor de bovenste week en vergelijk "
                    "het aantal respondenten met de kolom '# Respondenten' hierboven."
                )
            else:
                st.info("Nog geen data voor de afgelopen 3 weken.")

    st.markdown("---")

    # ── Ingestion log ────────────────────────────────────────
    st.subheader("📋 Ingestie geschiedenis")
    try:
        conn = get_connection()
        log_df = pd.read_sql_query(
            "SELECT timestamp, filename, segment, mode, rows_read, rows_inserted, "
            "rows_updated, rows_skipped, rows_error "
            "FROM ingestion_log ORDER BY timestamp DESC LIMIT 20",
            conn,
        )
        conn.close()
        if not log_df.empty:
            log_df = log_df.rename(columns={
                "timestamp": "Tijdstip",
                "filename": "Bestand",
                "segment": "Segment",
                "mode": "Modus",
                "rows_read": "Gelezen",
                "rows_inserted": "Ingevoegd",
                "rows_updated": "Bijgewerkt",
                "rows_skipped": "Overgeslagen",
                "rows_error": "Fouten",
            })
            st.dataframe(log_df, hide_index=True, width="stretch")
        else:
            st.info("Nog geen ingestie uitgevoerd.")
    except Exception:
        st.info("Nog geen ingestie uitgevoerd.")

    # ── Database stats ───────────────────────────────────────
    st.markdown("---")
    st.subheader("🗄️ Database statistieken")
    db_fresh = load_data()
    if not db_fresh.empty:
        ds1, ds2, ds3 = st.columns(3)
        with ds1:
            st.metric("Totaal responses", f"{len(db_fresh):,}")
        with ds2:
            scored_db = db_fresh[db_fresh["score"].notna()]
            st.metric("Met score", f"{len(scored_db):,}")
        with ds3:
            st.metric("Database bestand", os.path.basename(DB_PATH))
    else:
        st.info("Database is leeg. Upload CSV-bestanden hierboven.")
