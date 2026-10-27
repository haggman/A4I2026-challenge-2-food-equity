#!/usr/bin/env python3
"""Smoke test & verification script for Person A's BigQuery tools (`agent/tools.py`).

Run this in Google Cloud Shell (where ADC is pre-authenticated to `qwiklabs-gcp-04-ef48e08bc216`):
    python3 scripts/test_person_a_tools.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.tools import (  # noqa: E402
    check_shelf_life,
    ensure_embeddings_table,
    get_recipient_tract_equity,
    match_surplus_posting,
    split_large_load,
)
from agent.mcp_config import get_mcp_architecture_info  # noqa: E402


def main() -> None:
    print("=" * 76)
    print("PERSON A TOOLING VERIFICATION — ATLANTA RETAIL & GROCER RESCUE")
    print("=" * 76)

    # 1. Verify / materialize recipient_embeddings if needed
    print("\n[1/5] Checking/Materializing `a4i_food.recipient_embeddings`...")
    emb_info = ensure_embeddings_table()
    print(f"  -> {emb_info['table']}: {emb_info['rows_embedded']} rows embedded ({emb_info['embed_endpoint']})")

    # 2. Test check_shelf_life on "spinach" (the classic FoodKeeper subtitle trap)
    print("\n[2/5] Testing `check_shelf_life('spinach', 'refrigerated', 6.0)`...")
    sl = check_shelf_life("spinach", storage_state="refrigerated", donor_deadline_hours=6.0)
    print(f"  -> Matched Product : {sl['matched_product']}")
    print(f"  -> FoodKeeper Hours: {sl['shelf_life_hours']}h | Donor Window: {sl['donor_deadline_hours']}h")
    print(f"  -> Effective Clock : {sl['effective_window_hours']}h ({sl['clock_limiting_factor']})")

    # 3. Test match_surplus_posting on Retail Posting #1 (Spinach)
    posting = "10 crates of spinach, harvested yesterday, needs cold storage"
    print(f"\n[3/5] Testing `match_surplus_posting` on: {posting!r}...")
    res = match_surplus_posting(
        posting_text=posting,
        required_storage="refrigerated",
        pallets_needed=1,
        donor_deadline_hours=6.0,
        food_item="spinach",
        top_k=5,
    )

    print(f"\n  Eliminated Near-Misses ({len(res['eliminated_near_misses'])} caught):")
    for elim in res["eliminated_near_misses"][:5]:
        print(
            f"    - [Raw Vector #{elim['raw_vector_rank']} | dist={elim['vector_distance']:.4f}] "
            f"{elim['name']} (cold_storage={elim['cold_storage']}, max_pallets={elim['max_pallets']})\n"
            f"      Reason: {elim['elimination_reason']}"
        )

    if res.get("flagged_contradictions"):
        print(f"\n  Flagged Profile Contradictions ({len(res['flagged_contradictions'])}):")
        for fc in res["flagged_contradictions"]:
            print(f"    - {fc['name']}: {fc['contradiction_reasons'][0]}")

    print(f"\n  Top {len(res['ranked_matches'])} Viable Matches (Post-Filter + Equity Ranked):")
    for m in res["ranked_matches"]:
        ops = m["operational_capabilities"]
        eq = m["tract_equity"]
        print(
            f"    #{m['final_rank']} {m['name']} [{m['archetype_label']}]\n"
            f"       Address   : {m['address']}\n"
            f"       Scores    : composite={m['composite_score']:.4f} | vector_dist={m['vector_distance']:.4f} (raw rank #{m['raw_vector_rank']})\n"
            f"       Capability: cold={ops['cold_storage']}, dock={ops['loading_dock']}, reefer={ops['refrigerated_transport']}, max_pallets={ops['max_pallets']}\n"
            f"       Equity    : Tract {eq['tract_geo_id']} | poverty={eq['poverty_rate']:.1%} (metro {eq['metro_poverty_rate']:.1%}), no_vehicle={eq['no_vehicle_rate']:.1%} (metro {eq['metro_no_vehicle_rate']:.1%})\n"
            f"       Outreach  : {m['draft_outreach_message']}"
        )
        if m.get("tie_breaker_reason"):
            print(f"       Tie-Break : {m['tie_breaker_reason']}")

    # 4. Test get_recipient_tract_equity directly
    print("\n[4/5] Testing `get_recipient_tract_equity('Cedar Street Produce Alliance')`...")
    eq_res = get_recipient_tract_equity("Cedar Street Produce Alliance")
    print(f"  -> {eq_res.get('equity_summary')}")

    # 5. Test split_large_load on a 12-pallet refrigerated produce rescue
    print("\n[5/5] Testing `split_large_load` (12 pallets of perishable produce, 8h deadline)...")
    split_res = split_large_load(
        posting_text="12 pallets of mixed refrigerated grocer produce and dairy from 3 Atlanta stores",
        required_storage="refrigerated",
        total_pallets=12,
        donor_deadline_hours=8.0,
    )
    print(
        f"  -> Allocated {split_res['total_pallets_allocated']}/{split_res['total_pallets_requested']} pallets "
        f"across {split_res['number_of_stops']} stops (~{split_res['estimated_weekly_households_reached']:,} weekly households):"
    )
    for stop in split_res["allocation_plan"]:
        print(
            f"    Stop #{stop['stop_number']}: {stop['name']} -> {stop['pallets_allocated']} pallets "
            f"(max {stop['recipient_max_pallets']}, cold={stop['cold_storage']}, tract poverty={stop['tract_equity']['poverty_rate']:.1%})"
        )

    print("\n[MCP Info]", json.dumps(get_mcp_architecture_info(), indent=2))
    print("\nALL PERSON A TOOLS VERIFIED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
