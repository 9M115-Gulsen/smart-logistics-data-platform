TRUNCATE mart.mart_route_card;

INSERT INTO mart.mart_route_card
WITH base AS (
  SELECT
    date_trunc('month', pd.price_date)::date AS month,
    pc.loading_city_gcid, pc.unloading_city_gcid, pc.body_group, pc.weight_category,
    pc.volume_category, pc.price_id, pc.price_rub, 
    pc.price_rub / NULLIF(pc.distance, 0) AS price_km,
    pc.organization_id, pc.price_type
  FROM core.prices_clean pc
  JOIN price_dates pd ON pd.price_id = pc.price_id
  WHERE pc.is_fact AND NOT pc.complex
    AND pc.price_rub IS NOT NULL AND pc.distance > 0
    AND pc.outlier_mark = false
    AND pd.price_date <= '2026-10-26'
),
agg AS (
  SELECT month, loading_city_gcid, unloading_city_gcid, body_group, weight_category,
    percentile_cont(0.25) WITHIN GROUP (ORDER BY price_rub) AS p25_trip,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY price_rub) AS median_trip,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY price_rub) AS p75_trip,
    avg(price_rub) AS avg_trip,
    percentile_cont(0.25) WITHIN GROUP (ORDER BY price_km) AS p25_km,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY price_km) AS median_km,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY price_km) AS p75_km,
    count(DISTINCT price_id) AS trips_count,
    count(DISTINCT organization_id) FILTER (WHERE price_type IN (3,9)) AS carriers_count,
    CASE WHEN count(*) >= 2 AND avg(price_rub) <> 0
         THEN (stddev_samp(price_rub) / avg(price_rub))::numeric ELSE NULL::numeric END AS cv_rate,
    min(volume_category)::text AS volume_category
  FROM base
  GROUP BY 1,2,3,4,5
)
SELECT 
  a.month, a.loading_city_gcid, a.unloading_city_gcid, a.body_group, a.weight_category, a.volume_category,
  a.p25_trip, a.median_trip, a.p75_trip, a.avg_trip, a.p25_km, a.median_km, a.p75_km,
  a.trips_count, a.carriers_count, a.cv_rate,
  ((a.median_trip - LAG(a.median_trip) OVER w) / NULLIF(LAG(a.median_trip) OVER w, 0) * 100)::numeric AS mom_pct,
  ((a.median_trip - LAG(a.median_trip, 12) OVER w) / NULLIF(LAG(a.median_trip, 12) OVER w, 0) * 100)::numeric AS yoy_pct,
  CASE
    WHEN a.trips_count >= 30 AND a.carriers_count >= 5 AND ('2026-10-26'::date - a.month) <= 30 THEN 'HIGH'::text
    WHEN a.trips_count >= 10 THEN 'MEDIUM'::text
    ELSE 'LOW_DATA'::text
  END AS reliability_level
FROM agg a
WINDOW w AS (PARTITION BY loading_city_gcid, unloading_city_gcid, body_group, weight_category ORDER BY month);
