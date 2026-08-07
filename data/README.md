# data/

## `profile_components.json`

The archetype definitions and vocabulary banks the notebook uses to generate the operational
half of each recipient profile.

**Read it.** You should not trust generated data you cannot inspect, and neither should a
judge. Everything the generator can say about an organization is in this file: fourteen
archetypes, their storage and transport characteristics, and the phrasings they draw from.

The phrasing is modelled on real published operational profiles from Seattle/King County
(Public Domain) and Pennsylvania (US Government Works). The organizations themselves are real
and come from the IRS Exempt Organizations Business Master File at notebook runtime—they are
not in this file.

The `planted_cases` block at the bottom is worth particular attention. Those are the hard cases
we deliberately put in your corpus, and each one carries a `why`.

This file is ROI Training's own work and carries no restrictions.

## `foodkeeper.json`

USDA FSIS FoodKeeper shelf-life data—661 products, **CC0 public domain**. Source of record is
`https://www.foodsafety.gov/sites/default/files/foodkeeper_data_url_en.json`.

It is committed rather than downloaded because both USDA hosts return `403 Forbidden` to
requests from datacenter IP ranges, which is where every Colab runtime lives. The file has not
changed since 2018. The notebook still tries the live source first, so if USDA ever relaxes,
you will see it say so.

Note this is **consumer home-storage guidance for freshness and quality**, developed with
Cornell and the Food Marketing Institute. It is not a commercial cold-chain model—no
temperature setpoints, no pathogen-growth curves, and the assumed refrigerator temperature is
never stated. Right order of magnitude, wrong instrument for a guarantee. Say so if you use it
in a claim.

## Everything else

`.gitignore` excludes `*.csv` and `*.parquet` here. Data pulled by the notebook lives in
BigQuery, not in the repo—so this folder stays small and the repo stays cloneable on
conference wifi.
