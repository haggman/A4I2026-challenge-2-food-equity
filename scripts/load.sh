#!/usr/bin/env bash
#
# A4I 2026 - Challenge 2: Resilient Food Equity & Surplus Broker
# Headless fallback for notebooks/c2_01_load_explore.ipynb
#
# Rebuilds the same four BigQuery tables the notebook produces, from a
# pre-staged snapshot in Cloud Storage. Use this when a Colab Enterprise
# runtime is slow or unavailable, or when irs.gov is not cooperating.
#
# Run it from the repo root in Cloud Shell (no chmod needed - invoke with bash):
#     bash scripts/load.sh                # defaults to chicago
#     bash scripts/load.sh dallas
#     bash scripts/load.sh --list         # show available metros
#
# You still want the notebook if you can run it. It explains which half of the
# recipient data is real and which half we generated, and you will be asked
# about that. This script gets you the same tables without the teaching.

set -euo pipefail

BUCKET="gs://class-demo/a4i-2026/challenge-2-food-equity"
DATASET="a4i_food"
LOCATION="US"
TABLES=(recipients surplus_postings shelf_life tract_demographics)

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
info()  { printf '  %s\n' "$*"; }
fail()  { printf '\n\033[1mERROR:\033[0m %s\n\n%s\n\n' "$*" \
          "This script is safe to run again - every table load replaces whatever was there." >&2
          exit 1; }

on_interrupt() {
  printf '\n\n\033[1mInterrupted.\033[0m Nothing is broken.\n'
  printf 'Every load replaces the whole table, so just run this script again:\n'
  printf '    bash scripts/load.sh %s\n\n' "${METRO:-<metro>}"
  exit 130
}
trap on_interrupt INT TERM

list_metros() {
  bold "Metros available in the snapshot"
  if ! gcloud storage ls "${BUCKET}/" 2>/dev/null | sed 's|.*/\([^/]*\)/$|  \1|' | grep -v '^\s*$'; then
    fail "Could not list ${BUCKET}/. Check that you have network access."
  fi
  echo
  echo "Usage: bash scripts/load.sh <metro>"
}

# --------------------------------------------------------------------------
# Arguments
# --------------------------------------------------------------------------
METRO="${1:-chicago}"

if [[ "${METRO}" == "--list" || "${METRO}" == "-l" ]]; then
  list_metros
  exit 0
fi

if [[ "${METRO}" == "--help" || "${METRO}" == "-h" ]]; then
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

METRO="$(echo "${METRO}" | tr '[:upper:] ' '[:lower:]-')"
SRC="${BUCKET}/${METRO}"

# --------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------
bold "A4I Challenge 2 - loading data for: ${METRO}"
echo

command -v bq     >/dev/null 2>&1 || fail "'bq' not found. Run this in Cloud Shell."
command -v gcloud >/dev/null 2>&1 || fail "'gcloud' not found. Run this in Cloud Shell."

PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
[[ -n "${PROJECT_ID}" && "${PROJECT_ID}" != "(unset)" ]] \
  || fail "No project set. Run: gcloud config set project YOUR_PROJECT_ID"

info "Project : ${PROJECT_ID}"
info "Source  : ${SRC}"
info "Dataset : ${DATASET} (${LOCATION})"
echo

if ! gcloud storage ls "${SRC}/" >/dev/null 2>&1; then
  echo
  bold "No snapshot found for '${METRO}'."
  echo
  list_metros
  exit 1
fi

# --------------------------------------------------------------------------
# Create the dataset
# --------------------------------------------------------------------------
bold "1/3  Creating dataset"

# `bq ls -d NAME` does NOT ask "does this dataset exist". It lists the datasets
# inside a PROJECT called NAME, so it reports nothing for a dataset name and the
# script falls through to `mk`, which then dies on a dataset that is already
# there. That never shows up on a first run - it only bites on the second, which
# is exactly when you are re-running because something went wrong the first time.
# `show --dataset` with a fully qualified name is the question we actually mean.
dataset_exists() {
  bq --project_id="${PROJECT_ID}" show --dataset --format=none \
     "${PROJECT_ID}:${DATASET}" >/dev/null 2>&1
}

if dataset_exists; then
  info "${DATASET} already exists - reusing it"

  existing_loc="$(bq --project_id="${PROJECT_ID}" --format=json show --dataset \
                     "${PROJECT_ID}:${DATASET}" 2>/dev/null \
                  | tr ',' '\n' | grep -i '"location"' | head -1 \
                  | sed 's/.*: *"\([^"]*\)".*/\1/' || true)"
  if [[ -n "${existing_loc}" && "${existing_loc^^}" != "${LOCATION^^}" ]]; then
    fail "Dataset ${DATASET} already exists in '${existing_loc}', but this script loads into
       '${LOCATION}'. BigQuery cannot load across regions, and your embedding connection
       must live in the same region too. Either delete the dataset
       (bq rm -r -d ${DATASET}) or edit LOCATION at the top of this script to match."
  fi
else
  # Belt and braces. If the check above ever misfires, or two teammates run this
  # in the same shared project at the same second, "already exists" is a fine
  # outcome and not an error. Anything else is.
  if mk_out="$(bq --project_id="${PROJECT_ID}" --location="${LOCATION}" \
                  mk --dataset "${PROJECT_ID}:${DATASET}" 2>&1)"; then
    info "created ${DATASET}"
  elif grep -qi "already exists" <<<"${mk_out}"; then
    info "${DATASET} already exists - reusing it"
  else
    fail "Could not create dataset ${DATASET}:
       ${mk_out}"
  fi
fi
echo

# --------------------------------------------------------------------------
# Load each table
# --------------------------------------------------------------------------
# Every load uses --replace, so re-running from scratch is always safe.
bold "2/3  Loading tables"
for table in "${TABLES[@]}"; do
  uri="${SRC}/${table}/*.parquet"

  if ! gcloud storage ls "${SRC}/${table}/" >/dev/null 2>&1; then
    fail "Missing ${SRC}/${table}/. The snapshot for '${METRO}' looks incomplete - tell a coach."
  fi

  info "loading ${table}..."
  bq --project_id="${PROJECT_ID}" --location="${LOCATION}" load \
     --source_format=PARQUET \
     --replace \
     "${DATASET}.${table}" \
     "${uri}" >/dev/null

  info "  done"
done
echo

# --------------------------------------------------------------------------
# Verify - never trust a load you did not check
# --------------------------------------------------------------------------
bold "3/3  Verifying"
FAILED=0
for table in "${TABLES[@]}"; do
  rows="$(bq --project_id="${PROJECT_ID}" --location="${LOCATION}" \
            query --use_legacy_sql=false --format=csv \
            "SELECT COUNT(*) FROM \`${PROJECT_ID}.${DATASET}.${table}\`" \
          | tail -n 1)"

  if [[ "${rows}" == "0" ]]; then
    printf '  %-22s %s\n' "${table}" "0 rows  <-- EMPTY"
    FAILED=1
  else
    printf '  %-22s %s rows\n' "${table}" "${rows}"
  fi
done
echo

# The one number that decides whether vector search can work at all: if every
# profile were identical, the search would return ties in arbitrary order.
variety="$(bq --project_id="${PROJECT_ID}" --location="${LOCATION}" \
             query --use_legacy_sql=false --format=csv \
             "SELECT ROUND(100 * COUNT(DISTINCT profile_text) / COUNT(*), 1)
              FROM \`${PROJECT_ID}.${DATASET}.recipients\`" \
           | tail -n 1 || echo "")"

if [[ -n "${variety}" ]]; then
  info "Distinct recipient profiles: ${variety}%"
  info "(If that were near zero, every organization would look the same"
  info " to a vector search and ranking would be meaningless.)"
fi
echo

if [[ "${FAILED}" -eq 1 ]]; then
  fail "One or more tables loaded empty. Tell a coach before you build on this."
fi

bold "Ready."
echo
echo "  Your tables are in ${PROJECT_ID}.${DATASET}"
echo "  Safe to re-run at any time - each load replaces the whole table."
echo
echo "  IMPORTANT: the organizations in 'recipients' are real (IRS Exempt"
echo "  Organizations file). Their operational details are generated. The"
echo "  notebook explains which is which, and judges will ask you."
echo
echo "  Next: embed recipients.profile_text with AI.EMBED, then VECTOR_SEARCH it."
echo "  See the README for the syntax and the four traps."
echo
