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

## Everything else

`.gitignore` excludes `*.csv` and `*.parquet` here. Data pulled by the notebook lives in
BigQuery, not in the repo—so this folder stays small and the repo stays cloneable on
conference wifi.
