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
from datetime import datetime

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import (
    COLORS, CHART_COLORS, LOGO_CMYK, LOGO_WIT, DATA_DIR, DB_PATH,
)
from app.style import apply_style
from app.database import (
    get_connection, init_db, load_responses, load_issues,
    update_issue_status, log_ingestion,
)
from app.ingest import ingest_csv
from app.nps import calc_nps, nps_by_group, nps_trend, nps_yoy, leaderboard
from app.report import generate_week_report, generate_html_summary, generate_html_report, generate_theme_pdf
from app.wordcloud_engine import (
    extract_tfidf_terms, generate_wordcloud_image,
    compute_aspect_sentiment, compute_aspect_alerts,
    get_aspect_quotes, compute_aspect_yoy,
    ASPECT_ICONS,
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


@st.cache_data(ttl=60)
def load_issues_data():
    return load_issues()


get_db()


def refresh_data():
    load_data.clear()
    load_issues_data.clear()


# ============================================================
# Auto-ingest on first run if DB is empty
# ============================================================
def auto_ingest_if_needed():
    df = load_data()
    if df.empty:
        camping_path = os.path.join(DATA_DIR, "camping.csv")
        accom_path = os.path.join(DATA_DIR, "accommodaties.csv")
        if os.path.exists(camping_path) and os.path.exists(accom_path):
            with st.spinner("Data wordt geladen vanuit CSV bestanden..."):
                ingest_csv(camping_path, "Camping", "full_refresh")
                ingest_csv(accom_path, "Accommodaties", "full_refresh")
                refresh_data()
            st.success("Initiële data geladen!")
            st.rerun()


auto_ingest_if_needed()

# Load data
df = load_data()
issues_df = load_issues_data()


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
            "Actiepunten",
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

        # Period filter
        jaren = sorted(df["jaar"].dropna().unique())
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
        filtered = filtered[filtered["jaar"].isin(selected_jaren)]
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

    overall = calc_nps(scored)
    with col1:
        st.metric("Overall NPS", f"{overall['nps']:+.0f}" if overall else "-",
                   help="Alle vragen behalve vrije review")

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
# PAGE: Actiepunten
# ============================================================
elif page == "Actiepunten":
    st.title("Actiepunten")

    if issues_df.empty:
        st.info("Geen actiepunten gevonden. Laad eerst data via 'Data Bijwerken'.")
        st.stop()

    # Filters
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        filter_dept = st.multiselect("Afdeling", sorted(issues_df["afdeling"].unique()))
    with fc2:
        filter_prio = st.multiselect("Prioriteit", ["P1", "P2", "P3"])
    with fc3:
        filter_status = st.multiselect("Status", sorted(issues_df["status"].unique()),
                                       default=["nieuw"])
    with fc4:
        filter_segment_issues = st.multiselect("Segment", sorted(issues_df["segment"].dropna().unique()))

    filtered_issues = issues_df.copy()
    if filter_dept:
        filtered_issues = filtered_issues[filtered_issues["afdeling"].isin(filter_dept)]
    if filter_prio:
        filtered_issues = filtered_issues[filtered_issues["prioriteit"].isin(filter_prio)]
    if filter_status:
        filtered_issues = filtered_issues[filtered_issues["status"].isin(filter_status)]
    if filter_segment_issues:
        filtered_issues = filtered_issues[filtered_issues["segment"].isin(filter_segment_issues)]

    # Summary
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.metric("Totaal", len(filtered_issues))
    with s2:
        st.metric("P1 (Urgent)", len(filtered_issues[filtered_issues["prioriteit"] == "P1"]))
    with s3:
        st.metric("Nieuw", len(filtered_issues[filtered_issues["status"] == "nieuw"]))
    with s4:
        st.metric("In Behandeling",
                   len(filtered_issues[filtered_issues["status"] == "in behandeling"]))

    st.markdown("---")

    # Issues table
    display_cols = [
        "id", "prioriteit", "afdeling", "status", "objectnaam", "score",
        "tekst", "ingevuld_op", "segment",
    ]
    available_cols = [c for c in display_cols if c in filtered_issues.columns]
    st.dataframe(
        filtered_issues[available_cols].head(100),
        width="stretch",
        height=400,
    )

    # Status update
    st.markdown("---")
    st.subheader("Status Bijwerken")
    uc1, uc2, uc3, uc4 = st.columns([1, 1, 2, 1])
    with uc1:
        issue_id = st.number_input("Issue ID", min_value=1, step=1)
    with uc2:
        new_status = st.selectbox("Nieuwe status",
                                  ["nieuw", "in behandeling", "opgelost", "herzien"])
    with uc3:
        notitie = st.text_input("Notitie (optioneel)")
    with uc4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Opslaan"):
            update_issue_status(int(issue_id), new_status, notitie)
            st.success(f"Issue {issue_id} bijgewerkt naar '{new_status}'")
            refresh_data()
            st.rerun()

    # Export
    st.markdown("---")
    if st.button("Exporteer naar Excel"):
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            filtered_issues.to_excel(writer, index=False, sheet_name="Actiepunten")
        st.download_button(
            "Download Excel",
            output.getvalue(),
            file_name=f"actiepunten_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


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
        jaren_all = sorted(df["jaar"].dropna().unique())
        rapport_jaar = st.selectbox("Jaar", jaren_all,
                                    index=len(jaren_all) - 1 if jaren_all else 0)
    with rc2:
        weken = sorted(df[df["jaar"] == rapport_jaar]["week"].dropna().unique())
        rapport_week = st.selectbox("Week", weken,
                                    index=len(weken) - 1 if weken else 0)

    if st.button("Genereer Rapport"):
        with st.spinner("Rapport wordt gegenereerd..."):
            html = generate_html_report(df, issues_df, rapport_jaar, rapport_week)

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
        if not results.empty and results["jaar"].notna().any():
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

    aspect_df = compute_aspect_sentiment(text_data)

    if not aspect_df.empty:
        # Stacked horizontal bar chart: positive vs negative per aspect
        fig = go.Figure()

        # Reverse order so most-negative is on top visually
        plot_df = aspect_df.sort_values("pct_negatief", ascending=True)

        # Add icons to aspect labels and show mention count
        y_labels = [
            f'{ASPECT_ICONS.get(a, "")} {a} ({t})'
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
        st.plotly_chart(fig, width="stretch")

        # --- Export knop ---
        csv_export = aspect_df[["aspect", "positief", "negatief", "neutraal", "totaal", "pct_positief", "pct_negatief", "sentiment_score"]].copy()
        csv_export.columns = ["Aspect", "Positief", "Negatief", "Neutraal", "Totaal", "% Positief", "% Negatief", "Sentiment Score"]
        st.download_button(
            "📥 Exporteer aspect-data als CSV",
            csv_export.to_csv(index=False, sep=";").encode("utf-8-sig"),
            file_name=f"aspect_sentiment_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

        st.markdown("---")

        # --- Detail per aspect: YoY + quotes ---
        st.subheader("Detail per Aspect")
        st.markdown(
            f'<p style="color:{COLORS["tekst_licht"]}; font-size:14px; margin-top:-8px;">'
            f'Klik op een aspect voor jaar-op-jaar vergelijking en representatieve gastcitaten.</p>',
            unsafe_allow_html=True,
        )

        for _, row in aspect_df.iterrows():
            aspect_name = row["aspect"]
            totaal = int(row["totaal"])
            pct_neg = row["pct_negatief"]
            pct_pos = row["pct_positief"]
            sent_score = row["sentiment_score"]

            # Color of the badge based on sentiment
            if sent_score >= 30:
                badge_color = COLORS["diep_bosgroen"]
            elif sent_score >= 0:
                badge_color = COLORS["zandgroen"]
            else:
                badge_color = COLORS["heide_paars"]

            icon = ASPECT_ICONS.get(aspect_name, "")
            with st.expander(f"{icon} {aspect_name}  —  {totaal} mentions  |  {pct_pos:.0f}% positief  |  {pct_neg:.0f}% negatief"):
                # YoY comparison
                yoy = compute_aspect_yoy(fdf, aspect_name)
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

                # Quotes in two columns
                q_col1, q_col2 = st.columns(2)

                with q_col1:
                    st.markdown(f'**Negatieve citaten:**')
                    neg_quotes = get_aspect_quotes(text_data, aspect_name, "negative", 3)
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
                    pos_quotes = get_aspect_quotes(text_data, aspect_name, "positive", 3)
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
    else:
        st.info("Onvoldoende data voor aspect-analyse.")


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
    year_trend = nps_by_group(scored_soort, "jaar", min_responses=5)
    if not year_trend.empty:
        year_trend = year_trend.sort_values("jaar")
        fig = px.line(
            year_trend, x="jaar", y="nps",
            color_discrete_sequence=[COLORS["diep_bosgroen"]],
            markers=True,
            labels={"jaar": "Jaar", "nps": "NPS"},
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

        n_issues = len(issues_df[issues_df["objectsoort"] == dd_soort]) if not issues_df.empty else 0
        if n_issues > 0:
            summary_parts.append(f"Er zijn **{n_issues}** openstaande actiepunten voor dit type.")

        st.markdown("\n\n".join(summary_parts))


# ============================================================
# PAGE: Data Bijwerken
# ============================================================
elif page == "Data Bijwerken":
    st.title("Data Bijwerken")

    st.markdown("""
    Upload hier nieuwe enquêtedata. Je kunt een **volledige export** uploaden
    (Full Refresh) of alleen de **nieuwe week** toevoegen (Append).
    """)

    mode = st.radio(
        "Modus",
        ["Full Refresh (aanbevolen)", "Append (alleen nieuwe data)"],
        help="Full Refresh vervangt alle data voor het segment. Append voegt alleen nieuwe rijen toe.",
    )
    mode_key = "full_refresh" if "Full" in mode else "append"

    st.markdown("---")

    col_c, col_a = st.columns(2)

    with col_c:
        st.subheader("Camping")
        camping_file = st.file_uploader("Upload camping.csv", type=["csv"], key="camping")
        if camping_file and st.button("Verwerk Camping", key="btn_camping"):
            with st.spinner("Camping data wordt verwerkt..."):
                # Save temp file
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                    tmp.write(camping_file.getvalue())
                    tmp_path = tmp.name
                stats = ingest_csv(tmp_path, "Camping", mode_key)
                os.unlink(tmp_path)

            st.success("Camping data verwerkt!")
            st.json(stats)
            refresh_data()

    with col_a:
        st.subheader("Accommodaties")
        accom_file = st.file_uploader("Upload accommodaties.csv", type=["csv"], key="accom")
        if accom_file and st.button("Verwerk Accommodaties", key="btn_accom"):
            with st.spinner("Accommodatie data wordt verwerkt..."):
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                    tmp.write(accom_file.getvalue())
                    tmp_path = tmp.name
                stats = ingest_csv(tmp_path, "Accommodaties", mode_key)
                os.unlink(tmp_path)

            st.success("Accommodatie data verwerkt!")
            st.json(stats)
            refresh_data()

    # Ingestion log
    st.markdown("---")
    st.subheader("Ingestie Geschiedenis")
    try:
        conn = get_connection()
        log_df = pd.read_sql_query(
            "SELECT * FROM ingestion_log ORDER BY timestamp DESC LIMIT 20", conn
        )
        conn.close()
        if not log_df.empty:
            st.dataframe(log_df, width="stretch")
        else:
            st.info("Nog geen ingestie uitgevoerd.")
    except Exception:
        st.info("Nog geen ingestie uitgevoerd.")

    # Database stats
    st.markdown("---")
    st.subheader("Database Statistieken")
    if not df.empty:
        ds1, ds2, ds3 = st.columns(3)
        with ds1:
            st.metric("Totaal Responses", f"{len(df):,}")
        with ds2:
            st.metric("Totaal Issues", f"{len(issues_df):,}")
        with ds3:
            st.metric("Database", os.path.basename(DB_PATH))
