-- Embed every recipient profile once. Follows notebook Section 14.
--
-- Model: gemini-embedding-2 (3072 dims). The query side MUST use the same endpoint;
-- vectors from different models are not comparable. Switching models means re-running this.
--
-- AI.EMBED returns STRUCT<result ARRAY<FLOAT64>, status STRING>. We keep .result and drop
-- any row whose status is non-empty (a failed embedding), so the search never ranks garbage.
--
-- No vector index: at ~130 short profiles the index never populates (needs ~10 MB).
-- Searches pass use_brute_force instead.
--
-- Re-run whenever a4i_food.recipients is reloaded. Atlanta, 2026-10-27: 127/127 embedded.

CREATE OR REPLACE TABLE `a4i_food.recipient_embeddings` AS
SELECT
  * EXCEPT (embedded),
  embedded.result AS embedding
FROM (
  SELECT r.*, AI.EMBED(r.profile_text, endpoint => 'gemini-embedding-2') AS embedded
  FROM `a4i_food.recipients` r
)
WHERE embedded.status = '';
