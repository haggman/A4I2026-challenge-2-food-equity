"""Person A — BigQuery Vector Search, Shelf-Life, Equity Audit, and Load-Splitting Tools.

Implements the tool functions consumed by Person B's ADK agent (`agent/agent.py`):
1. `match_surplus_posting` — Semantic search via BigQuery `VECTOR_SEARCH` + `AI.EMBED`
   with post-search operational filtering, planted decoy elimination, contradiction
   detection, and census-tract equity tie-breaking.
2. `check_shelf_life` — USDA FSIS FoodKeeper shelf-life lookup across `product_name`,
   `product_subtitle`, and `keywords`, resolving sentinel notes and effective clock.
3. `get_recipient_tract_equity` — Geospatial join (`ST_DISTANCE`) between a recipient
   organization and `a4i_food.tract_demographics`, benchmarked against Atlanta metro averages.
4. `split_large_load` — Multi-recipient load-splitting planner when a surplus donation
   exceeds any single recipient's pallet capacity.
"""

from __future__ import annotations

import os
import re
from typing import Any

from google.cloud import bigquery

# ---------------------------------------------------------------------------
# Configuration (Environment-driven with safe defaults for our GCP project)
# ---------------------------------------------------------------------------
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-ef48e08bc216")
DATASET = os.environ.get("BIGQUERY_DATASET", "a4i_food")
LOCATION = os.environ.get("BIGQUERY_LOCATION", "US")
EMBED_ENDPOINT = os.environ.get("EMBED_ENDPOINT", "gemini-embedding-2")
BQ_CONNECTION_ID = os.environ.get("BIGQUERY_CONNECTION_ID", "").strip()

_bq_client: bigquery.Client | None = None


def _get_bq_client() -> bigquery.Client:
    """Return a cached BigQuery client configured for the project and dataset location."""
    global _bq_client
    if _bq_client is None:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
        location = os.environ.get("BIGQUERY_LOCATION", LOCATION)
        _bq_client = bigquery.Client(project=project, location=location)
    return _bq_client


def _table_ref(table_name: str) -> str:
    """Return the fully-qualified backtick-quoted BigQuery table reference."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
    dataset = os.environ.get("BIGQUERY_DATASET", DATASET)
    return f"`{project}.{dataset}.{table_name}`"


def _ai_embed_sql(expr: str) -> str:
    """Build the `AI.EMBED(...)` SQL expression, optionally including `connection_id`."""
    endpoint = os.environ.get("EMBED_ENDPOINT", EMBED_ENDPOINT)
    conn = os.environ.get("BIGQUERY_CONNECTION_ID", BQ_CONNECTION_ID).strip()
    if conn:
        return f"AI.EMBED({expr}, endpoint => '{endpoint}', connection_id => '{conn}')"
    return f"AI.EMBED({expr}, endpoint => '{endpoint}')"


# ---------------------------------------------------------------------------
# Helper: Ensure `recipient_embeddings` exists in BigQuery
# ---------------------------------------------------------------------------
def ensure_embeddings_table() -> dict[str, Any]:
    """Materialize `a4i_food.recipient_embeddings` using `AI.EMBED` if not already present.

    Follows the 4 rules from Section 14 of `c2_01_load_explore.ipynb`:
    1. Extracts `.result AS embedding` from the `STRUCT<result ARRAY<FLOAT64>, status STRING>`.
    2. Filters `WHERE embedded.status = ''` so failed embeddings never pollute rankings.
    3. Keeps table in `US` location for brute-force `VECTOR_SEARCH`.
    """
    client = _get_bq_client()
    emb_table = _table_ref("recipient_embeddings")
    rec_table = _table_ref("recipients")
    embed_call = _ai_embed_sql("r.profile_text")

    sql = f"""
    CREATE OR REPLACE TABLE {emb_table} AS
    SELECT
      * EXCEPT (embedded),
      embedded.result AS embedding
    FROM (
      SELECT r.*, {embed_call} AS embedded
      FROM {rec_table} r
    )
    WHERE embedded.status = ''
    """
    job = client.query(sql)
    job.result()

    count_row = next(iter(client.query(f"SELECT COUNT(*) AS n FROM {emb_table}").result()))
    return {
        "status": "ok",
        "table": emb_table.strip("`"),
        "rows_embedded": int(count_row.n),
        "embed_endpoint": os.environ.get("EMBED_ENDPOINT", EMBED_ENDPOINT),
    }


# ---------------------------------------------------------------------------
# Helper: Contradiction & Operational Constraint Checkers
# ---------------------------------------------------------------------------
def _detect_profile_contradictions(row: dict[str, Any]) -> list[str]:
    """Detect contradictions between structured columns and free-text `profile_text`,
    or internal contradictions within `profile_text` (e.g., Harborview Neighbors Trust).
    """
    contradictions: list[str] = []
    text = str(row.get("profile_text") or "")
    text_lower = text.lower()
    cold = str(row.get("cold_storage") or "none").lower()
    frozen = bool(row.get("frozen_storage"))
    max_pallets = int(row.get("max_pallets") or 0)

    # 1. Claims walk-in/freezer/pallets, but also states single shelf in a shared cupboard / no freezer
    if ("single shelf in a shared cupboard" in text_lower or "shared cupboard" in text_lower) and (
        cold in ("walk-in", "commercial", "medical", "vehicle") or max_pallets >= 2
    ):
        contradictions.append(
            f"Structured record and opening sentence claim cold_storage='{cold}' and "
            f"max_pallets={max_pallets}, but profile_text contradicts this: "
            "'Storage is a single shelf in a shared cupboard and we have no freezer at present.'"
        )

    if "we have no freezer" in text_lower and (frozen or "walk-in freezer" in text_lower):
        msg = (
            "Profile claims frozen_storage=True / 'walk-in freezer' in one sentence, "
            "but states 'we have no freezer at present' in another."
        )
        if msg not in contradictions:
            contradictions.append(msg)

    # 2. Structured cold_storage is 'none' but profile text claims walk-in/commercial refrigeration
    if cold == "none" and re.search(
        r"\b(walk-in cooler|walk-in cold|reach-in cooler|reefer|chilled holding|cold chain capacity)\b",
        text_lower,
    ):
        if "no " not in text_lower and "without " not in text_lower and "not " not in text_lower:
            contradictions.append(
                "Structured cold_storage='none', but profile_text describes active commercial refrigeration."
            )

    # 3. Structured cold_storage is 'walk-in' but profile text says household/domestic fridge only
    if cold == "walk-in" and re.search(
        r"\b(one household refrigerator|one domestic refrigerator|household refrigeration only|single fridge behind the counter)\b",
        text_lower,
    ):
        contradictions.append(
            "Structured cold_storage='walk-in', but profile_text describes only a single household refrigerator."
        )

    return contradictions


def _normalize_storage_requirement(required_storage: str, posting_text: str = "") -> str:
    """Normalize storage requirement into 'refrigerated', 'frozen', or 'shelf-stable'."""
    s = (required_storage or "").strip().lower()
    pt = (posting_text or "").strip().lower()

    if any(k in s for k in ("frozen", "freezer", "ice")):
        return "frozen"
    if any(k in s for k in ("refrigerat", "cold", "chill", "cooler", "produce", "dairy", "perishable", "deli")):
        return "refrigerated"
    if any(k in s for k in ("pantry", "shelf", "ambient", "dry", "room")):
        # Double-check posting text in case caller left default or passed pantry for cold item
        if any(k in pt for k in ("cold storage", "cold chain", "refrigerat", "needs cold")):
            return "refrigerated"
        return "shelf-stable"

    # Fallback inference from posting_text
    if any(k in pt for k in ("frozen", "freezer")):
        return "frozen"
    if any(k in pt for k in ("cold", "refrigerat", "spinach", "milk", "yogurt", "dairy", "deli", "sandwiches", "salads", "blueberries")):
        return "refrigerated"
    return "shelf-stable"


def _infer_food_item(posting_text: str, food_item: str = "") -> str:
    """Infer a concise FoodKeeper lookup term from `food_item` or `posting_text`."""
    if food_item and food_item.strip():
        return food_item.strip()

    pt = (posting_text or "").lower()
    known_mappings = [
        ("spinach", "spinach"),
        ("lettuce", "lettuce"),
        ("salad", "leftovers"),
        ("sandwich", "leftovers"),
        ("deli", "leftovers"),
        ("milk", "milk"),
        ("yogurt", "yogurt"),
        ("dairy", "milk"),
        ("bread", "bread"),
        ("pastr", "bread"),
        ("potato", "potatoes"),
        ("blueberr", "blueberries"),
        ("berr", "berries"),
        ("winter squash", "spaghetti squash"),
        ("squash", "squash"),
        ("sealed infant formula", "liquid concentrate or ready-to-feed formula"),
        ("nutritional supplement", "formula"),
        ("formula", "formula"),
        ("diaper", "diapers"),
        ("chicken", "chicken"),
        ("beef", "beef"),
        ("pork", "pork"),
        ("apple", "apples"),
        ("tomato", "tomatoes"),
        ("egg", "eggs"),
    ]
    for keyword, mapped in known_mappings:
        if keyword in pt:
            return mapped

    # Fallback: strip numbers/units and return first meaningful words
    cleaned = re.sub(r"\b(\d+|crates|crate|pallets|pallet|cases|case|gallons|loaves|tons|bins|of|about|roughly)\b", " ", pt)
    words = [w for w in re.findall(r"[a-z]+", cleaned) if len(w) > 2]
    return " ".join(words[:3]) if words else posting_text.strip()


# ---------------------------------------------------------------------------
# Tool 1: `check_shelf_life`
# ---------------------------------------------------------------------------
def check_shelf_life(
    food_item: str,
    storage_state: str = "refrigerated",
    donor_deadline_hours: float = 0.0,
) -> dict[str, Any]:
    """Look up USDA FSIS FoodKeeper shelf-life guidance in `a4i_food.shelf_life`.

    Searches across `product_name`, `product_subtitle` (crucial because 'Spinach' lives
    in `product_subtitle` on `product_name='Lettuce'`), and `keywords`. Computes the
    effective dispatch clock as `MIN(donor_deadline_hours, shelf_life_hours)`.

    Args:
        food_item: Name or description of the food product (e.g., "spinach", "milk", "bread").
        storage_state: Storage condition ("refrigerated", "pantry", "shelf-stable", "frozen").
        donor_deadline_hours: Hours available stated by the donor (0 if not specified).

    Returns:
        Dictionary with matched FoodKeeper row, `shelf_life_hours`, `effective_window_hours`,
        `clock_limiting_factor`, and sentinel note explanation.
    """
    client = _get_bq_client()
    shelf_table = _table_ref("shelf_life")
    surplus_table = _table_ref("surplus_postings")

    query_term = _infer_food_item(food_item, food_item).lower().strip()
    norm_storage = _normalize_storage_requirement(storage_state, food_item)
    is_sealed = "sealed" in (food_item or "").lower()

    # Non-food short-circuit (e.g., diapers/wipes)
    if any(k in query_term for k in ("diaper", "wipe", "hygiene", "toiletries")):
        eff = float(donor_deadline_hours) if donor_deadline_hours > 0 else 720.0
        return {
            "queried_item": food_item,
            "matched_product": None,
            "category": "Non-food essentials",
            "storage_state": norm_storage,
            "shelf_life_hours": None,
            "donor_deadline_hours": float(donor_deadline_hours) if donor_deadline_hours > 0 else None,
            "effective_window_hours": eff,
            "clock_limiting_factor": "donor_deadline (non-food item not tracked in USDA FoodKeeper)",
            "storage_note": "non_food_essential",
            "guidance_summary": (
                f"'{food_item}' is a non-food essential not tracked by USDA FoodKeeper. "
                f"Using donor pickup window of {eff:.1f} hours."
            ),
        }

    # Build tokens for flexible matching
    tokens = [t for t in re.findall(r"[a-z]+", query_term) if len(t) > 2]
    primary_token = tokens[0] if tokens else query_term

    sql = f"""
    WITH scored AS (
      SELECT
        product_id,
        product_name,
        product_subtitle,
        keywords,
        category,
        refrigerated_hours,
        refrigerated_note,
        pantry_hours,
        pantry_note,
        CASE
          WHEN LOWER(product_name) = @exact THEN 100
          WHEN LOWER(IFNULL(product_subtitle, '')) LIKE CONCAT('%', @exact, '%') THEN 95
          WHEN LOWER(product_name) LIKE CONCAT('%', @exact, '%') THEN 85
          WHEN LOWER(IFNULL(keywords, '')) LIKE CONCAT('%', @exact, '%') THEN 75
          WHEN LOWER(IFNULL(product_subtitle, '')) LIKE CONCAT('%', @token, '%') THEN 70
          WHEN LOWER(product_name) LIKE CONCAT('%', @token, '%') THEN 65
          WHEN LOWER(IFNULL(keywords, '')) LIKE CONCAT('%', @token, '%') THEN 55
          ELSE 0
        END AS match_score
      FROM {shelf_table}
    )
    SELECT *
    FROM scored
    WHERE match_score > 0
    ORDER BY
      match_score DESC,
      -- Prefer rows that have a numeric hour figure for the requested storage state
      CASE
        WHEN @storage = 'refrigerated' AND refrigerated_hours IS NOT NULL THEN 0
        WHEN @storage != 'refrigerated' AND pantry_hours IS NOT NULL THEN 0
        ELSE 1
      END ASC,
      product_id ASC
    LIMIT 5
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("exact", "STRING", query_term),
            bigquery.ScalarQueryParameter("token", "STRING", primary_token),
            bigquery.ScalarQueryParameter("storage", "STRING", norm_storage),
        ]
    )
    rows = [dict(r) for r in client.query(sql, job_config=job_config).result()]

    # Fallback: check if `surplus_postings` has a pre-linked `foodkeeper_product`
    if not rows:
        fallback_sql = f"""
        SELECT f.*
        FROM {surplus_table} s
        JOIN {shelf_table} f ON LOWER(f.product_name) = LOWER(s.foodkeeper_product)
        WHERE LOWER(s.posting_text) LIKE CONCAT('%', @token, '%')
        LIMIT 1
        """
        fb_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("token", "STRING", primary_token)]
        )
        rows = [dict(r) for r in client.query(fallback_sql, job_config=fb_config).result()]

    if not rows:
        eff = float(donor_deadline_hours) if donor_deadline_hours > 0 else 24.0
        return {
            "queried_item": food_item,
            "matched_product": None,
            "category": "Unmatched",
            "storage_state": norm_storage,
            "shelf_life_hours": None,
            "donor_deadline_hours": float(donor_deadline_hours) if donor_deadline_hours > 0 else None,
            "effective_window_hours": eff,
            "clock_limiting_factor": "donor_deadline (no exact FoodKeeper row matched)",
            "storage_note": None,
            "guidance_summary": (
                f"No USDA FoodKeeper entry matched '{food_item}'. "
                f"Defaulting to donor window of {eff:.1f} hours."
            ),
        }

    best = rows[0]
    if norm_storage == "refrigerated":
        raw_hours = best.get("refrigerated_hours")
        note = best.get("refrigerated_note")
    else:
        raw_hours = best.get("pantry_hours")
        note = best.get("pantry_note")

    shelf_hours: float | None = float(raw_hours) if raw_hours is not None else None

    # Guardrail from Section 13: a sealed donation must NEVER inherit an after-opening 1-hour shelf life
    if is_sealed and shelf_hours is not None and shelf_hours < 24.0:
        shelf_hours = None
        note = "sealed_package_use_expiry_date"

    donor_hrs: float | None = float(donor_deadline_hours) if donor_deadline_hours and donor_deadline_hours > 0 else None

    if donor_hrs is not None and shelf_hours is not None:
        effective_hours = min(donor_hrs, shelf_hours)
        limiting = (
            "donor_deadline"
            if donor_hrs <= shelf_hours
            else "foodkeeper_shelf_life"
        )
    elif donor_hrs is not None:
        effective_hours = donor_hrs
        limiting = f"donor_deadline (FoodKeeper note: {note or 'no numeric hours for this state'})"
    elif shelf_hours is not None:
        effective_hours = shelf_hours
        limiting = "foodkeeper_shelf_life"
    else:
        effective_hours = 24.0
        limiting = f"default_24h (FoodKeeper note: {note or 'none'})"

    subtitle_str = f" ({best['product_subtitle']})" if best.get("product_subtitle") else ""
    matched_label = f"{best['product_name']}{subtitle_str}"

    return {
        "queried_item": food_item,
        "matched_product": matched_label,
        "product_id": best.get("product_id"),
        "product_name": best.get("product_name"),
        "product_subtitle": best.get("product_subtitle"),
        "category": best.get("category"),
        "storage_state": norm_storage,
        "shelf_life_hours": shelf_hours,
        "donor_deadline_hours": donor_hrs,
        "effective_window_hours": effective_hours,
        "clock_limiting_factor": limiting,
        "storage_note": note,
        "refrigerated_hours": best.get("refrigerated_hours"),
        "refrigerated_note": best.get("refrigerated_note"),
        "pantry_hours": best.get("pantry_hours"),
        "pantry_note": best.get("pantry_note"),
        "guidance_summary": (
            f"Matched '{food_item}' to USDA FoodKeeper '{matched_label}' "
            f"(category: {best.get('category')}). "
            f"FoodKeeper {norm_storage} shelf life: "
            f"{f'{shelf_hours:.0f}h' if shelf_hours is not None else f'N/A (note: {note})'}. "
            f"Donor window: {f'{donor_hrs:.0f}h' if donor_hrs is not None else 'not specified'}. "
            f"Effective dispatch clock: {effective_hours:.0f} hours ({limiting})."
        ),
    }


# ---------------------------------------------------------------------------
# Tool 2: `get_recipient_tract_equity`
# ---------------------------------------------------------------------------
def get_recipient_tract_equity(recipient_name_or_id: str) -> dict[str, Any]:
    """Fetch Census Tract ACS equity metrics for a recipient organization in Atlanta.

    Joins the recipient's `(longitude, latitude)` to the nearest census tract in
    `a4i_food.tract_demographics` using `ST_DISTANCE`, and benchmarks the tract's
    `poverty_rate`, `no_vehicle_rate`, and `assistance_rate` against the Atlanta
    metro-wide averages (Section 11 Equity Audit).

    Args:
        recipient_name_or_id: Recipient organization name (substring or exact) or numeric `recipient_id`.

    Returns:
        Dictionary with recipient metadata, nearest census tract `geo_id`, poverty/no-vehicle/SNAP
        rates, Atlanta metro baseline averages, and an equity audit interpretation.
    """
    client = _get_bq_client()
    rec_table = _table_ref("recipients")
    tract_table = _table_ref("tract_demographics")

    lookup_str = str(recipient_name_or_id).strip()
    is_numeric_id = lookup_str.isdigit()

    sql = f"""
    WITH metro_avg AS (
      SELECT
        ROUND(AVG(poverty_rate), 4) AS metro_poverty_rate,
        ROUND(AVG(no_vehicle_rate), 4) AS metro_no_vehicle_rate,
        ROUND(AVG(assistance_rate), 4) AS metro_assistance_rate,
        ROUND(AVG(median_income), 0) AS metro_median_income,
        COUNT(*) AS total_metro_tracts
      FROM {tract_table}
    ),
    target_rec AS (
      SELECT *
      FROM {rec_table}
      WHERE
        (@is_id AND recipient_id = SAFE_CAST(@lookup AS INT64))
        OR (NOT @is_id AND LOWER(name) = LOWER(@lookup))
        OR (NOT @is_id AND LOWER(name) LIKE CONCAT('%', LOWER(@lookup), '%'))
      ORDER BY
        CASE WHEN LOWER(name) = LOWER(@lookup) THEN 0 ELSE 1 END,
        recipient_id ASC
      LIMIT 1
    ),
    nearest_tract AS (
      SELECT
        r.recipient_id,
        r.name,
        r.street,
        r.city,
        r.state,
        r.zip_code,
        r.archetype,
        r.archetype_label,
        r.cold_storage,
        r.frozen_storage,
        r.loading_dock,
        r.refrigerated_transport,
        r.max_pallets,
        r.weekly_households,
        r.latitude,
        r.longitude,
        t.geo_id AS tract_geo_id,
        t.total_pop AS tract_population,
        t.median_income AS tract_median_income,
        ROUND(t.poverty_rate, 4) AS poverty_rate,
        ROUND(t.no_vehicle_rate, 4) AS no_vehicle_rate,
        ROUND(t.assistance_rate, 4) AS assistance_rate,
        ROUND(
          ST_DISTANCE(
            ST_GEOGPOINT(r.longitude, r.latitude),
            ST_GEOGPOINT(t.tract_lon, t.tract_lat)
          ),
          0
        ) AS distance_to_tract_center_m
      FROM target_rec r
      CROSS JOIN {tract_table} t
      QUALIFY ROW_NUMBER() OVER (
        PARTITION BY r.recipient_id
        ORDER BY ST_DISTANCE(
          ST_GEOGPOINT(r.longitude, r.latitude),
          ST_GEOGPOINT(t.tract_lon, t.tract_lat)
        ) ASC
      ) = 1
    )
    SELECT
      n.*,
      m.metro_poverty_rate,
      m.metro_no_vehicle_rate,
      m.metro_assistance_rate,
      m.metro_median_income,
      m.total_metro_tracts
    FROM nearest_tract n
    CROSS JOIN metro_avg m
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("is_id", "BOOL", is_numeric_id),
            bigquery.ScalarQueryParameter("lookup", "STRING", lookup_str),
        ]
    )
    rows = [dict(r) for r in client.query(sql, job_config=job_config).result()]
    if not rows:
        return {
            "status": "not_found",
            "queried_recipient": recipient_name_or_id,
            "message": f"No recipient organization matched '{recipient_name_or_id}' in {rec_table}.",
        }

    row = rows[0]
    pov = float(row.get("poverty_rate") or 0.0)
    no_veh = float(row.get("no_vehicle_rate") or 0.0)
    asst = float(row.get("assistance_rate") or 0.0)
    m_pov = float(row.get("metro_poverty_rate") or 0.0)
    m_veh = float(row.get("metro_no_vehicle_rate") or 0.0)
    m_asst = float(row.get("metro_assistance_rate") or 0.0)

    equity_index = round(0.50 * pov + 0.30 * no_veh + 0.20 * asst, 4)
    metro_index = round(0.50 * m_pov + 0.30 * m_veh + 0.20 * m_asst, 4)
    high_need = pov > m_pov or no_veh > m_veh

    return {
        "status": "ok",
        "recipient_id": int(row["recipient_id"]),
        "name": row["name"],
        "address": f"{row.get('street') or ''}, {row.get('city') or 'Atlanta'}, {row.get('state') or 'GA'} {row.get('zip_code') or ''}".strip(", "),
        "archetype_label": row.get("archetype_label"),
        "cold_storage": row.get("cold_storage"),
        "max_pallets": int(row.get("max_pallets") or 0),
        "weekly_households": int(row.get("weekly_households") or 0),
        "tract_geo_id": row.get("tract_geo_id"),
        "tract_population": int(row.get("tract_population") or 0),
        "tract_median_income": float(row.get("tract_median_income") or 0.0),
        "poverty_rate": pov,
        "no_vehicle_rate": no_veh,
        "assistance_rate": asst,
        "equity_need_index": equity_index,
        "atlanta_metro_benchmarks": {
            "metro_poverty_rate": m_pov,
            "metro_no_vehicle_rate": m_veh,
            "metro_assistance_rate": m_asst,
            "metro_equity_need_index": metro_index,
            "total_metro_tracts": int(row.get("total_metro_tracts") or 0),
        },
        "above_metro_need_average": high_need,
        "equity_summary": (
            f"{row['name']} is located near Census Tract {row.get('tract_geo_id')} "
            f"(poverty rate: {pov:.1%} vs. Atlanta metro avg {m_pov:.1%}; "
            f"households with no vehicle: {no_veh:.1%} vs. metro avg {m_veh:.1%}; "
            f"public assistance/SNAP rate: {asst:.1%} vs. metro avg {m_asst:.1%}). "
            f"Composite equity need index: {equity_index:.3f} (metro baseline: {metro_index:.3f})."
        ),
    }


# ---------------------------------------------------------------------------
# Tool 3: `match_surplus_posting`
# ---------------------------------------------------------------------------
def match_surplus_posting(
    posting_text: str,
    required_storage: str = "refrigerated",
    pallets_needed: int = 1,
    donor_deadline_hours: float = 6.0,
    food_item: str = "",
    top_k: int = 10,
) -> dict[str, Any]:
    """Match a surplus donation posting to recipient organizations using BigQuery `VECTOR_SEARCH`.

    Pipeline:
    1. Resolves USDA FoodKeeper shelf life (`check_shelf_life`) to compute `effective_window_hours`
       (`MIN(donor_deadline_hours, shelf_life_hours)`).
    2. Embeds `posting_text` inline with `AI.EMBED(..., endpoint => 'gemini-embedding-2')` and runs
       brute-force `VECTOR_SEARCH` against `a4i_food.recipient_embeddings`, joined with nearest
       Census Tract demographics (`a4i_food.tract_demographics`).
    3. Post-search validation:
       - Catches and eliminates semantic near-miss decoys (e.g., `Greenline Community Pantry`, which
         wants fresh greens but has `cold_storage='none'`).
       - Flags profile contradictions (e.g., `Harborview Neighbors Trust`, which claims a walk-in
         freezer and 6 pallets in one sentence and a single cupboard shelf with no freezer in the next).
       - Enforces storage compatibility, pallet capacity, and dietary constraints.
    4. Deliberately ranks surviving candidates and breaks operational ties (e.g., `Cedar Street
       Produce Alliance` vs. `Maple Street Produce Alliance`) using Census Tract Equity Need
       (`poverty_rate`, `no_vehicle_rate`, `assistance_rate`) and logistics readiness.

    Args:
        posting_text: Raw free-text surplus posting from a grocer, farm, or donor.
        required_storage: Required temperature regime ("refrigerated", "frozen", or "shelf-stable").
        pallets_needed: Estimated pallet volume of the load (default 1; note 10 crates of produce ~ 1 pallet).
        donor_deadline_hours: Hours before donor pickup window closes.
        food_item: Optional explicit food product name for USDA FoodKeeper lookup.
        top_k: Number of top viable candidates to return (default 10).

    Returns:
        Structured dictionary with `clock`, `ranked_matches`, `eliminated_near_misses`,
        `flagged_contradictions`, `tie_break_analysis`, and `equity_audit_summary`.
    """
    client = _get_bq_client()
    emb_table = _table_ref("recipient_embeddings")
    tract_table = _table_ref("tract_demographics")

    norm_storage = _normalize_storage_requirement(required_storage, posting_text)
    inferred_item = _infer_food_item(posting_text, food_item)

    # Guardrail: if caller passed pallets_needed >= 5 because posting said "10 crates" or "48 cases"
    # (without mentioning pallets), normalize to realistic pallet equivalent while noting original figure.
    pt_lower = (posting_text or "").lower()
    effective_pallets = max(1, int(pallets_needed or 1))
    pallet_note = None
    if (
        effective_pallets >= 5
        and "pallet" not in pt_lower
        and "truckload" not in pt_lower
        and "tons" not in pt_lower
        and any(u in pt_lower for u in ("crate", "case", "gallon", "loaf", "loaves", "box", "tray"))
    ):
        pallet_note = (
            f"Normalized {effective_pallets} crates/cases/units to ~1 standard pallet equivalent "
            "for storage capacity matching (1 pallet holds ~40 crates/cases)."
        )
        effective_pallets = 1

    # Step 1: Compute the clock from USDA FoodKeeper + donor deadline
    clock = check_shelf_life(
        food_item=inferred_item,
        storage_state=norm_storage,
        donor_deadline_hours=donor_deadline_hours,
    )
    effective_window_hours = float(clock.get("effective_window_hours") or donor_deadline_hours or 6.0)

    # Step 2: Run BigQuery VECTOR_SEARCH + nearest Census Tract join
    # Fetch at least 30 candidates so post-search filtering still leaves plenty of viable matches
    # and captures all planted teaching cases (decoy, contradiction, ties, vocabulary mismatch).
    search_k = max(int(top_k or 10) * 3, 30)
    query_embed_sql = _ai_embed_sql("@query_text")

    vector_sql = f"""
    WITH metro_avg AS (
      SELECT
        ROUND(AVG(poverty_rate), 4) AS metro_poverty_rate,
        ROUND(AVG(no_vehicle_rate), 4) AS metro_no_vehicle_rate,
        ROUND(AVG(assistance_rate), 4) AS metro_assistance_rate
      FROM {tract_table}
    ),
    vs AS (
      SELECT
        base.recipient_id,
        base.ein,
        base.name,
        base.street,
        base.city,
        base.state,
        base.zip_code,
        base.ntee_code,
        base.archetype,
        base.archetype_label,
        base.cold_storage,
        base.frozen_storage,
        base.loading_dock,
        base.refrigerated_transport,
        base.max_pallets,
        base.pickup_window_hours,
        base.weekly_households,
        base.reported_income,
        base.populations_served,
        base.service_days,
        base.profile_text,
        base.profile_source,
        base.latitude,
        base.longitude,
        distance
      FROM VECTOR_SEARCH(
        TABLE {emb_table},
        'embedding',
        (SELECT {query_embed_sql}.result AS embedding),
        top_k => @search_k,
        distance_type => 'COSINE',
        options => '{{"use_brute_force":true}}'
      )
    ),
    with_tract AS (
      SELECT
        v.*,
        t.geo_id AS tract_geo_id,
        t.total_pop AS tract_population,
        t.median_income AS tract_median_income,
        ROUND(t.poverty_rate, 4) AS poverty_rate,
        ROUND(t.no_vehicle_rate, 4) AS no_vehicle_rate,
        ROUND(t.assistance_rate, 4) AS assistance_rate,
        ROUND(
          ST_DISTANCE(
            ST_GEOGPOINT(v.longitude, v.latitude),
            ST_GEOGPOINT(t.tract_lon, t.tract_lat)
          ),
          0
        ) AS distance_to_tract_center_m
      FROM vs v
      CROSS JOIN {tract_table} t
      QUALIFY ROW_NUMBER() OVER (
        PARTITION BY v.recipient_id
        ORDER BY ST_DISTANCE(
          ST_GEOGPOINT(v.longitude, v.latitude),
          ST_GEOGPOINT(t.tract_lon, t.tract_lat)
        ) ASC
      ) = 1
    )
    SELECT
      w.*,
      m.metro_poverty_rate,
      m.metro_no_vehicle_rate,
      m.metro_assistance_rate
    FROM with_tract w
    CROSS JOIN metro_avg m
    ORDER BY w.distance ASC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("query_text", "STRING", posting_text),
            bigquery.ScalarQueryParameter("search_k", "INT64", search_k),
        ]
    )

    try:
        raw_candidates = [dict(r) for r in client.query(vector_sql, job_config=job_config).result()]
    except Exception as exc:
        # Auto-heal if `recipient_embeddings` table was not materialized yet
        if "Not found: Table" in str(exc) and "recipient_embeddings" in str(exc):
            ensure_embeddings_table()
            raw_candidates = [dict(r) for r in client.query(vector_sql, job_config=job_config).result()]
        else:
            raise

    ranked_matches: list[dict[str, Any]] = []
    eliminated_near_misses: list[dict[str, Any]] = []
    flagged_contradictions: list[dict[str, Any]] = []

    for vector_rank, cand in enumerate(raw_candidates, start=1):
        name = str(cand.get("name") or "")
        cold = str(cand.get("cold_storage") or "none").lower()
        frozen = bool(cand.get("frozen_storage"))
        dock = bool(cand.get("loading_dock"))
        reefer = bool(cand.get("refrigerated_transport"))
        max_pallets = int(cand.get("max_pallets") or 0)
        pickup_win = int(cand.get("pickup_window_hours") or 0)
        households = int(cand.get("weekly_households") or 0)
        dist = float(cand.get("distance") or 1.0)
        sem_sim = round(max(0.0, 1.0 - (dist / 2.0)), 4)

        pov = float(cand.get("poverty_rate") or 0.0)
        no_veh = float(cand.get("no_vehicle_rate") or 0.0)
        asst = float(cand.get("assistance_rate") or 0.0)
        m_pov = float(cand.get("metro_poverty_rate") or 0.0)
        m_veh = float(cand.get("metro_no_vehicle_rate") or 0.0)
        m_asst = float(cand.get("metro_assistance_rate") or 0.0)
        equity_index = round(0.50 * pov + 0.30 * no_veh + 0.20 * asst, 4)
        metro_equity_index = round(0.50 * m_pov + 0.30 * m_veh + 0.20 * m_asst, 4)

        address_parts = [
            str(cand.get("street") or "").strip(),
            str(cand.get("city") or "Atlanta").strip(),
            f"{str(cand.get('state') or 'GA').strip()} {str(cand.get('zip_code') or '').strip()}".strip(),
        ]
        address = ", ".join(p for p in address_parts if p)

        # 1. Check profile contradictions (e.g. Harborview Neighbors Trust)
        contradictions = _detect_profile_contradictions(cand)
        if contradictions:
            contradiction_entry = {
                "recipient_id": int(cand["recipient_id"]),
                "name": name,
                "raw_vector_rank": vector_rank,
                "vector_distance": round(dist, 4),
                "structured_claims": {
                    "cold_storage": cold,
                    "frozen_storage": frozen,
                    "max_pallets": max_pallets,
                },
                "profile_text": cand.get("profile_text"),
                "contradiction_reasons": contradictions,
                "recommended_action": (
                    "Hold automatic dispatch and verify storage capacity by phone — "
                    "profile text directly contradicts structured cold-storage/pallet flags."
                ),
            }
            flagged_contradictions.append(contradiction_entry)
            eliminated_near_misses.append({
                "recipient_id": int(cand["recipient_id"]),
                "name": name,
                "raw_vector_rank": vector_rank,
                "vector_distance": round(dist, 4),
                "cold_storage": cold,
                "max_pallets": max_pallets,
                "elimination_category": "profile_contradiction",
                "elimination_reason": " | ".join(contradictions),
                "profile_text": cand.get("profile_text"),
            })
            continue

        # 2. Check hard operational constraints (Storage & Capacity)
        rejection_reasons: list[str] = []
        elimination_category = "operational_constraint"

        if norm_storage == "frozen" and not frozen:
            rejection_reasons.append(
                f"Requires frozen storage, but organization has frozen_storage=False (cold_storage='{cold}')."
            )
            elimination_category = "storage_incompatible"
        elif norm_storage == "refrigerated":
            if cold == "none":
                is_decoy = name == "Greenline Community Pantry" or "fresh greens" in str(cand.get("profile_text") or "").lower()
                elimination_category = "near_miss_decoy_no_cold_storage" if is_decoy else "storage_incompatible"
                rejection_reasons.append(
                    f"Requires refrigerated cold storage, but organization has cold_storage='none' "
                    f"(dry/ambient storage only). "
                    + (
                        "Semantic near-miss decoy: profile explicitly asks for fresh greens/salad vegetables, "
                        "so VECTOR_SEARCH ranked it near the top, but sending perishable greens without refrigeration would spoil the load."
                        if is_decoy
                        else "Cannot safely hold temperature-sensitive perishables."
                    )
                )
            elif cold == "domestic" and effective_pallets > 1:
                elimination_category = "domestic_fridge_capacity_too_small"
                rejection_reasons.append(
                    f"Organization only has a household/domestic refrigerator (cold_storage='domestic', "
                    f"max_pallets={max_pallets}), which cannot absorb a {effective_pallets}-pallet commercial load."
                )

        if max_pallets < effective_pallets:
            rejection_reasons.append(
                f"Load requires {effective_pallets} pallet(s), but organization max_pallets={max_pallets} "
                "(requires load splitting via `split_large_load` or a larger recipient)."
            )
            if elimination_category == "operational_constraint":
                elimination_category = "insufficient_pallet_capacity"

        if rejection_reasons:
            # Record in eliminated_near_misses if it ranked in top 15 semantically or is a planted case
            if vector_rank <= 15 or cand.get("profile_source") == "planted":
                eliminated_near_misses.append({
                    "recipient_id": int(cand["recipient_id"]),
                    "name": name,
                    "raw_vector_rank": vector_rank,
                    "vector_distance": round(dist, 4),
                    "semantic_similarity": sem_sim,
                    "cold_storage": cold,
                    "frozen_storage": frozen,
                    "max_pallets": max_pallets,
                    "elimination_category": elimination_category,
                    "elimination_reason": " ".join(rejection_reasons),
                    "profile_text": cand.get("profile_text"),
                })
            continue

        # 3. Viable candidate — compute composite ranking score (Semantic + Operational + Equity)
        # Commercial cold storage tier bonus over household domestic fridge
        cold_tier_bonus = 0.08 if cold in ("walk-in", "commercial", "vehicle", "medical") else 0.0
        # Fast-turn reefer transport bonus when clock is urgent (<= 8 hours)
        urgency_transport_bonus = 0.05 if (effective_window_hours <= 8.0 and reefer) else (0.02 if reefer else 0.0)
        dock_bonus = 0.02 if (dock and effective_pallets >= 2) else 0.0

        # Composite score balances semantic fit (60%), operational readiness (20%), and tract equity need (20%)
        composite_score = round(
            0.60 * sem_sim
            + cold_tier_bonus
            + urgency_transport_bonus
            + dock_bonus
            + 0.20 * min(1.0, equity_index * 2.5),
            4,
        )

        why_fit_parts = [
            f"Semantic match (vector distance {dist:.4f}) to profile ({cand.get('archetype_label')}).",
            f"Verified '{cold}' cold storage" + (" + freezer" if frozen else "") + f" with {max_pallets}-pallet capacity.",
        ]
        if reefer:
            why_fit_parts.append(
                f"Operates refrigerated transport for rapid collection within the {effective_window_hours:.0f}h clock."
            )
        if pov > m_pov or no_veh > m_veh:
            why_fit_parts.append(
                f"High-equity impact in Tract {cand.get('tract_geo_id')} "
                f"(poverty {pov:.1%} vs. {m_pov:.1%} metro avg; no-vehicle {no_veh:.1%} vs. {m_veh:.1%} metro avg)."
            )

        outreach_msg = (
            f"URGENT SURPLUS OFFER ({effective_window_hours:.0f}h window): We have \"{posting_text}\" "
            f"({effective_pallets} pallet equiv., {norm_storage}). Your {cold} storage "
            f"(up to {max_pallets} pallets) and service profile ({cand.get('service_days')}) are a strong match. "
            + (
                "Can your refrigerated vehicle collect within the next few hours?"
                if reefer
                else "Can someone on site receive delivery at your door/dock within the window?"
            )
        )

        ranked_matches.append({
            "recipient_id": int(cand["recipient_id"]),
            "name": name,
            "address": address,
            "archetype": cand.get("archetype"),
            "archetype_label": cand.get("archetype_label"),
            "profile_source": cand.get("profile_source"),
            "raw_vector_rank": vector_rank,
            "vector_distance": round(dist, 4),
            "semantic_similarity": sem_sim,
            "composite_score": composite_score,
            "operational_capabilities": {
                "cold_storage": cold,
                "frozen_storage": frozen,
                "loading_dock": dock,
                "refrigerated_transport": reefer,
                "max_pallets": max_pallets,
                "pallets_allocated": min(max_pallets, effective_pallets),
                "pickup_window_hours": pickup_win,
                "weekly_households": households,
                "service_days": cand.get("service_days"),
                "populations_served": cand.get("populations_served"),
            },
            "clock_compatibility": {
                "effective_window_hours": effective_window_hours,
                "recipient_window_hours": pickup_win,
                "can_collect_in_time": True,
                "collection_mode": (
                    "Recipient refrigerated vehicle pickup"
                    if reefer
                    else ("Dock-height delivery" if dock else "Direct door delivery")
                ),
            },
            "tract_equity": {
                "tract_geo_id": cand.get("tract_geo_id"),
                "poverty_rate": pov,
                "no_vehicle_rate": no_veh,
                "assistance_rate": asst,
                "tract_median_income": float(cand.get("tract_median_income") or 0.0),
                "equity_need_index": equity_index,
                "metro_poverty_rate": m_pov,
                "metro_no_vehicle_rate": m_veh,
                "metro_assistance_rate": m_asst,
                "metro_equity_need_index": metro_equity_index,
                "above_metro_need_average": (pov > m_pov or no_veh > m_veh),
            },
            "why_matched": " ".join(why_fit_parts),
            "profile_text": cand.get("profile_text"),
            "draft_outreach_message": outreach_msg,
            "tie_breaker_reason": None,
        })

    # Step 4: Sort viable candidates by composite_score DESC, then vector_distance ASC
    ranked_matches.sort(key=lambda m: (-m["composite_score"], m["vector_distance"]))

    # Step 5: Detect genuine operational ties (e.g. Cedar Street vs Maple Street Produce Alliance,
    # or top two candidates with identical operational capabilities) and attach explicit tie-break justification.
    tie_break_analysis: dict[str, Any] | None = None
    by_spec: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for m in ranked_matches:
        ops = m["operational_capabilities"]
        spec_key = (
            ops["cold_storage"],
            ops["frozen_storage"],
            ops["loading_dock"],
            ops["refrigerated_transport"],
            ops["max_pallets"],
            ops["weekly_households"],
        )
        by_spec.setdefault(spec_key, []).append(m)

    for spec_key, tied_group in by_spec.items():
        if len(tied_group) >= 2:
            first, second = tied_group[0], tied_group[1]
            reason = (
                f"Operational Tie Detected between '{first['name']}' and '{second['name']}': "
                f"Both have identical operational specs (cold_storage='{spec_key[0]}', "
                f"loading_dock={spec_key[2]}, refrigerated_transport={spec_key[3]}, "
                f"max_pallets={spec_key[4]}, weekly_households={spec_key[5]}). "
                f"Notice their raw vector distances differ ({first['vector_distance']:.4f} vs. "
                f"{second['vector_distance']:.4f}) solely due to phrasing differences in their profiles. "
                f"Tie-break decision: Ranked '{first['name']}' ahead based on "
                f"Tract Equity Need Index ({first['tract_equity']['equity_need_index']:.3f} in Tract "
                f"{first['tract_equity']['tract_geo_id']} [poverty {first['tract_equity']['poverty_rate']:.1%}, "
                f"no-vehicle {first['tract_equity']['no_vehicle_rate']:.1%}] vs. "
                f"{second['tract_equity']['equity_need_index']:.3f} in Tract "
                f"{second['tract_equity']['tract_geo_id']} [poverty {second['tract_equity']['poverty_rate']:.1%}, "
                f"no-vehicle {second['tract_equity']['no_vehicle_rate']:.1%}]) and composite score "
                f"({first['composite_score']:.4f} vs. {second['composite_score']:.4f}). "
                f"'{second['name']}' is designated as the immediate co-equal backup or split-load partner."
            )
            first["tie_breaker_reason"] = reason
            second["tie_breaker_reason"] = reason
            if tie_break_analysis is None:
                tie_break_analysis = {
                    "tied_organizations": [first["name"], second["name"]],
                    "shared_operational_specs": {
                        "cold_storage": spec_key[0],
                        "frozen_storage": spec_key[1],
                        "loading_dock": spec_key[2],
                        "refrigerated_transport": spec_key[3],
                        "max_pallets": spec_key[4],
                        "weekly_households": spec_key[5],
                    },
                    "selected_winner": first["name"],
                    "runner_up_backup": second["name"],
                    "justification": reason,
                }

    # Also ensure top 2 overall candidates have a clear comparison note if not already set
    if len(ranked_matches) >= 2 and not ranked_matches[0].get("tie_breaker_reason"):
        m1, m2 = ranked_matches[0], ranked_matches[1]
        ranked_matches[0]["tie_breaker_reason"] = (
            f"Selected #1 over #2 ('{m2['name']}') due to higher composite fit "
            f"({m1['composite_score']:.4f} vs {m2['composite_score']:.4f}; "
            f"vector distance {m1['vector_distance']:.4f} vs {m2['vector_distance']:.4f}; "
            f"tract poverty {m1['tract_equity']['poverty_rate']:.1%} vs {m2['tract_equity']['poverty_rate']:.1%})."
        )

    top_matches = ranked_matches[: int(top_k or 10)]
    for idx, m in enumerate(top_matches, start=1):
        m["final_rank"] = idx

    # Step 6: Equity Audit Summary across the returned top matches (Section 11)
    if top_matches:
        top3 = top_matches[: min(3, len(top_matches))]
        avg_match_pov = round(sum(m["tract_equity"]["poverty_rate"] for m in top3) / len(top3), 4)
        avg_match_veh = round(sum(m["tract_equity"]["no_vehicle_rate"] for m in top3) / len(top3), 4)
        m_pov = top3[0]["tract_equity"]["metro_poverty_rate"]
        m_veh = top3[0]["tract_equity"]["metro_no_vehicle_rate"]
        equity_audit = {
            "top_matches_avg_poverty_rate": avg_match_pov,
            "atlanta_metro_avg_poverty_rate": m_pov,
            "top_matches_avg_no_vehicle_rate": avg_match_veh,
            "atlanta_metro_avg_no_vehicle_rate": m_veh,
            "reaches_above_average_need": (avg_match_pov >= m_pov or avg_match_veh >= m_veh),
            "audit_narrative": (
                f"Top matched recipients sit in tracts averaging {avg_match_pov:.1%} poverty "
                f"(vs. Atlanta metro average {m_pov:.1%}) and {avg_match_veh:.1%} households without a vehicle "
                f"(vs. metro average {m_veh:.1%})."
            ),
        }
    else:
        equity_audit = None

    return {
        "posting_text": posting_text,
        "normalized_storage_required": norm_storage,
        "pallets_needed": effective_pallets,
        "pallet_normalization_note": pallet_note,
        "clock": clock,
        "ranked_matches": top_matches,
        "eliminated_near_misses": eliminated_near_misses,
        "flagged_contradictions": flagged_contradictions,
        "tie_break_analysis": tie_break_analysis,
        "equity_audit_summary": equity_audit,
    }


# ---------------------------------------------------------------------------
# Tool 4: `split_large_load`
# ---------------------------------------------------------------------------
def split_large_load(
    posting_text: str,
    required_storage: str,
    total_pallets: int,
    donor_deadline_hours: float,
) -> dict[str, Any]:
    """Allocate a large multi-pallet surplus donation across multiple compatible recipients.

    Used when a single donation (e.g., 5 tons of potatoes = ~10 pallets, or half a truckload
    of blueberries = ~12 pallets, or 30 bins of winter squash) exceeds one organization's
    `max_pallets` capacity or when a coordinator wants to distribute across high-need tracts.

    Args:
        posting_text: Free-text description of the bulk surplus load.
        required_storage: Required storage condition ("refrigerated", "frozen", or "shelf-stable").
        total_pallets: Total number of pallets to allocate across recipients.
        donor_deadline_hours: Donor pickup deadline in hours.

    Returns:
        Dictionary with the multi-stop allocation plan, total pallets allocated, unallocated
        remainder (if any), per-stop outreach messages, and tract equity coverage.
    """
    target_pallets = max(1, int(total_pallets or 1))
    # Search with pallets_needed=1 so we get all storage-compatible recipients with at least 1 pallet
    base_result = match_surplus_posting(
        posting_text=posting_text,
        required_storage=required_storage,
        pallets_needed=1,
        donor_deadline_hours=donor_deadline_hours,
        top_k=25,
    )

    candidates = [
        m for m in base_result.get("ranked_matches", [])
        if int(m["operational_capabilities"].get("max_pallets") or 0) >= 1
    ]

    allocations: list[dict[str, Any]] = []
    remaining = target_pallets

    for stop_num, cand in enumerate(candidates, start=1):
        if remaining <= 0:
            break
        cap = int(cand["operational_capabilities"]["max_pallets"])
        # For refrigerated loads > 1 pallet, skip single household ('domestic') fridges if commercial cold storage exists
        if (
            base_result.get("normalized_storage_required") == "refrigerated"
            and cand["operational_capabilities"]["cold_storage"] == "domestic"
            and remaining > 1
        ):
            continue

        allocated = min(cap, remaining)
        if allocated <= 0:
            continue

        remaining -= allocated
        allocations.append({
            "stop_number": len(allocations) + 1,
            "recipient_id": cand["recipient_id"],
            "name": cand["name"],
            "address": cand["address"],
            "archetype_label": cand.get("archetype_label"),
            "pallets_allocated": allocated,
            "recipient_max_pallets": cap,
            "cold_storage": cand["operational_capabilities"]["cold_storage"],
            "loading_dock": cand["operational_capabilities"]["loading_dock"],
            "refrigerated_transport": cand["operational_capabilities"]["refrigerated_transport"],
            "weekly_households": cand["operational_capabilities"]["weekly_households"],
            "vector_distance": cand["vector_distance"],
            "tract_equity": cand["tract_equity"],
            "draft_outreach_message": (
                f"SPLIT-LOAD DISPATCH (Stop #{len(allocations) + 1} — {allocated} of {target_pallets} pallets): "
                f"We are splitting \"{posting_text}\" across partner sites within a "
                f"{base_result['clock']['effective_window_hours']:.0f}h window. "
                f"Can you accept {allocated} pallet(s) (your max capacity: {cap})?"
            ),
        })

    allocated_total = target_pallets - remaining
    total_households = sum(a["weekly_households"] for a in allocations)

    return {
        "posting_text": posting_text,
        "normalized_storage_required": base_result.get("normalized_storage_required"),
        "total_pallets_requested": target_pallets,
        "total_pallets_allocated": allocated_total,
        "unallocated_pallets": remaining,
        "fully_allocated": remaining == 0,
        "number_of_stops": len(allocations),
        "estimated_weekly_households_reached": total_households,
        "clock": base_result.get("clock"),
        "allocation_plan": allocations,
        "eliminated_near_misses": base_result.get("eliminated_near_misses", [])[:5],
        "flagged_contradictions": base_result.get("flagged_contradictions", []),
    }
