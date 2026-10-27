-- Candidate generation: the semantic half of the matcher. This is the query the agent's
-- vector-search tool wraps.
--
-- Parameters:
--   @posting_text  STRING  the surplus offer, as the donor typed it
--   @top_k         INT64   how many candidates to return (20 leaves room for the filter)
--
-- This is a CANDIDATE list, not an answer. The top hits include organizations that want the
-- food and cannot store it (for spinach, the planted "Greenline Community Pantry" ranks #2
-- with cold_storage = 'none'). The storage / pallet / pickup-window filter runs after this.
--
-- distance is cosine distance: lower is closer. The endpoint must match the one that built
-- recipient_embeddings (gemini-embedding-2).

SELECT
  base.recipient_id,
  base.name,
  base.street,
  base.city,
  base.zip_code,
  base.archetype_label,
  base.profile_source,
  base.cold_storage,
  base.frozen_storage,
  base.loading_dock,
  base.refrigerated_transport,
  base.max_pallets,
  base.pickup_window_hours,
  base.service_days,
  base.weekly_households,
  base.populations_served,
  base.latitude,
  base.longitude,
  base.profile_text,
  ROUND(distance, 4) AS distance
FROM VECTOR_SEARCH(
  TABLE `a4i_food.recipient_embeddings`, 'embedding',
  (SELECT AI.EMBED(@posting_text, endpoint => 'gemini-embedding-2').result AS embedding),
  top_k => @top_k,
  distance_type => 'COSINE',
  options => '{"use_brute_force": true}')
ORDER BY distance;
