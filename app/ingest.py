"""
Westerbergen Guest Insights - Data ingestion from CSV to SQLite
"""
import pandas as pd
from datetime import datetime
from app.config import VRAAG_CATEGORIE, VRAAG_LABEL, NPS_PROMOTER_MIN, NPS_PASSIVE_MIN
from app.database import get_connection, init_db, compute_unique_key, log_ingestion


def _classify_nps(score):
    """Classify a score into NPS group."""
    if pd.isna(score):
        return None
    score = float(score)
    if score >= NPS_PROMOTER_MIN:
        return "promoter"
    elif score >= NPS_PASSIVE_MIN:
        return "passive"
    else:
        return "detractor"


def _match_vraag_key(vraag_text, mapping):
    """Fuzzy match a question text to our mapping keys."""
    if not vraag_text:
        return None
    vraag_lower = vraag_text.lower().strip()
    for key, value in mapping.items():
        if key.lower() in vraag_lower or vraag_lower in key.lower():
            return value
    # Fallback partial matches
    if "gastvriendelijk" in vraag_lower:
        return mapping.get("Hoe ervaart u de gastvriendelijkheid op het park?")
    if "kindvriendelijk" in vraag_lower or "kind vriendelijk" in vraag_lower:
        return mapping.get("Hoe beoordeelt u de kind vriendelijkheid van het park?")
    if "supermarkt" in vraag_lower:
        return mapping.get("Hoe tevreden bent u met de supermarkt op het park?")
    if "eetgelegenhe" in vraag_lower:
        return mapping.get("Wat vond u van de eetgelegenheden op het park?")
    if "accommodatie" in vraag_lower and "schoonmaak" not in vraag_lower and "prijs" not in vraag_lower:
        return mapping.get("Hoe tevreden bent u met de accommodatie?")
    if "kampeerplaats" in vraag_lower and "prijs" not in vraag_lower:
        return mapping.get("Hoe tevreden bent u met de kampeerplaats?")
    if "schoonmaak" in vraag_lower:
        return mapping.get("Hoe tevreden bent u over de schoonmaak van uw accommodatie?")
    if "sanitair" in vraag_lower:
        return mapping.get("Hoe tevreden bent u over het sanitair gebouwen/privé sanitair?")
    if "prijs" in vraag_lower and "accommodatie" in vraag_lower:
        return mapping.get("Bent u tevreden over de prijs/kwaliteit verhouding van de accommodatie?")
    if "prijs" in vraag_lower and ("kampeerplaats" in vraag_lower or "kampeerplek" in vraag_lower):
        return mapping.get("Bent u tevreden over de prijs/kwaliteit verhouding van de kampeerplaats?") or \
               mapping.get("Bent u tevreden over de prijs/kwaliteit verhouding van de kampeerplek?")
    if "algemene oordeel" in vraag_lower or "algemeen oordeel" in vraag_lower:
        return mapping.get("Wat is uw algemene oordeel over uw verblijf?")
    if "algemene review" in vraag_lower:
        return mapping.get("Algemene review (niet verplicht)")
    return None


def parse_csv(filepath, segment):
    """Parse a CSV file and return a cleaned DataFrame."""
    df = pd.read_csv(
        filepath,
        sep=";",
        quotechar='"',
        encoding="latin-1",
        dtype=str,
        on_bad_lines="skip",
    )

    # Drop trailing empty columns
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]

    # Rename columns to snake_case
    col_map = {
        "Reserveringsnummer": "reserveringsnummer",
        "Relatie": "relatie",
        "Aankomst": "aankomst",
        "Vertrek": "vertrek",
        "Ingevuld op": "ingevuld_op",
        "Objectsoort": "objectsoort",
        "Objectnaam": "objectnaam",
        "Verhuurmodel": "verhuurmodel",
        "Vraag": "vraag",
        "Antwoord": "antwoord",
        "Aanvulling": "aanvulling",
    }
    df = df.rename(columns=col_map)

    # Add segment
    df["segment"] = segment

    # Parse score (numeric from antwoord)
    df["score"] = pd.to_numeric(df["antwoord"], errors="coerce")

    # Map category and label
    df["categorie"] = df["vraag"].apply(lambda v: _match_vraag_key(v, VRAAG_CATEGORIE))
    df["vraag_label"] = df["vraag"].apply(lambda v: _match_vraag_key(v, VRAAG_LABEL))

    # Parse dates
    df["ingevuld_op"] = pd.to_datetime(df["ingevuld_op"], errors="coerce")
    df["aankomst"] = pd.to_datetime(df["aankomst"], errors="coerce")
    df["vertrek"] = pd.to_datetime(df["vertrek"], errors="coerce")

    # Extract time components
    df["jaar"] = df["ingevuld_op"].dt.isocalendar().year.astype("Int64")
    df["week"] = df["ingevuld_op"].dt.isocalendar().week.astype("Int64")
    df["maand"] = df["ingevuld_op"].dt.month.astype("Int64")

    # NPS classification
    df["nps_groep"] = df["score"].apply(_classify_nps)

    # Compute unique key
    df["unique_key"] = df.apply(
        lambda row: compute_unique_key({
            "reserveringsnummer": row.get("reserveringsnummer", ""),
            "vraag": row.get("vraag", ""),
            "ingevuld_op": str(row.get("ingevuld_op", "")),
            "segment": row.get("segment", ""),
        }),
        axis=1,
    )

    # Clean text fields
    for col in ["aanvulling", "relatie", "objectsoort", "objectnaam"]:
        df[col] = df[col].fillna("").str.strip()

    # Clean objectsoort (remove XXX markers for archived)
    df["objectsoort"] = df["objectsoort"].str.replace(r"^XXXArchief\s*", "", regex=True)
    df["objectsoort"] = df["objectsoort"].str.replace(r"XXX$", "", regex=True)
    df["objectsoort"] = df["objectsoort"].str.replace(r"^XXX\s*", "", regex=True)
    df["objectsoort"] = df["objectsoort"].str.strip()

    # Clean objectnaam
    df["objectnaam"] = df["objectnaam"].str.replace(r"^XXX\s*", "", regex=True)
    df["objectnaam"] = df["objectnaam"].str.replace(r"\s*XXX$", "", regex=True)
    df["objectnaam"] = df["objectnaam"].str.strip()

    return df


def ingest_csv(filepath, segment, mode="full_refresh"):
    """
    Ingest a CSV file into the database.

    mode: 'full_refresh' or 'append'
    Returns ingestion stats dict.
    """
    conn = get_connection()
    init_db(conn)

    df = parse_csv(filepath, segment)
    now = datetime.now().isoformat()

    stats = {"read": len(df), "inserted": 0, "updated": 0, "skipped": 0, "error": 0}

    if mode == "full_refresh":
        # Delete child rows in issues table first (foreign key constraint)
        conn.execute(
            "DELETE FROM issues WHERE unique_key IN "
            "(SELECT unique_key FROM responses_raw WHERE segment = ?)",
            (segment,),
        )
        conn.execute("DELETE FROM responses_raw WHERE segment = ?", (segment,))
        conn.commit()

    # Convert datetime columns to string for SQLite
    df_db = df.copy()
    for col in ["ingevuld_op", "aankomst", "vertrek"]:
        df_db[col] = df_db[col].astype(str).replace("NaT", None)

    for _, row in df_db.iterrows():
        try:
            uk = row["unique_key"]

            if mode == "append":
                existing = conn.execute(
                    "SELECT unique_key FROM responses_raw WHERE unique_key = ?",
                    (uk,),
                ).fetchone()

                if existing:
                    # Update
                    conn.execute("""
                        UPDATE responses_raw SET
                            reserveringsnummer=?, relatie=?, aankomst=?, vertrek=?,
                            ingevuld_op=?, objectsoort=?, objectnaam=?, verhuurmodel=?,
                            vraag=?, antwoord=?, aanvulling=?, segment=?, categorie=?,
                            vraag_label=?, score=?, jaar=?, week=?, maand=?,
                            nps_groep=?, updated_at=?
                        WHERE unique_key=?
                    """, (
                        row["reserveringsnummer"], row["relatie"], row["aankomst"],
                        row["vertrek"], row["ingevuld_op"], row["objectsoort"],
                        row["objectnaam"], row["verhuurmodel"], row["vraag"],
                        row["antwoord"], row["aanvulling"], row["segment"],
                        row["categorie"], row["vraag_label"],
                        None if pd.isna(row["score"]) else float(row["score"]),
                        None if pd.isna(row["jaar"]) else int(row["jaar"]),
                        None if pd.isna(row["week"]) else int(row["week"]),
                        None if pd.isna(row["maand"]) else int(row["maand"]),
                        row["nps_groep"], now, uk,
                    ))
                    stats["updated"] += 1
                    continue

            # Insert new row
            conn.execute("""
                INSERT OR IGNORE INTO responses_raw
                    (unique_key, reserveringsnummer, relatie, aankomst, vertrek,
                     ingevuld_op, objectsoort, objectnaam, verhuurmodel, vraag,
                     antwoord, aanvulling, segment, categorie, vraag_label,
                     score, jaar, week, maand, nps_groep, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                uk, row["reserveringsnummer"], row["relatie"], row["aankomst"],
                row["vertrek"], row["ingevuld_op"], row["objectsoort"],
                row["objectnaam"], row["verhuurmodel"], row["vraag"],
                row["antwoord"], row["aanvulling"], row["segment"],
                row["categorie"], row["vraag_label"],
                None if pd.isna(row["score"]) else float(row["score"]),
                None if pd.isna(row["jaar"]) else int(row["jaar"]),
                None if pd.isna(row["week"]) else int(row["week"]),
                None if pd.isna(row["maand"]) else int(row["maand"]),
                row["nps_groep"], now, now,
            ))
            stats["inserted"] += 1

        except Exception as e:
            stats["error"] += 1
            stats["details"] = stats.get("details", "") + f"\n{str(e)[:200]}"

    conn.commit()

    stats["skipped"] = stats["read"] - stats["inserted"] - stats["updated"] - stats["error"]
    log_ingestion(conn, filepath if isinstance(filepath, str) else filepath.name,
                  segment, mode, stats)
    conn.close()
    return stats


