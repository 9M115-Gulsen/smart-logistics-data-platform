CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS dq;
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE IF NOT EXISTS dq.quarantine_prices (
    price_id BIGINT,
    reason_code TEXT,
    quarantined_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.prices_clean (
    price_id BIGINT PRIMARY KEY,
    loading_date DATE,
    loading_city_gcid INT,
    unloading_city_gcid INT,
    distance NUMERIC,
    total_weight NUMERIC,
    total_volume NUMERIC,
    body_group TEXT,
    weight_category TEXT,
    volume_category TEXT,
    price_rub NUMERIC,
    price_type INT,
    is_fact BOOLEAN,
    complex BOOLEAN,
    outlier_mark BOOLEAN,
    organization_id BIGINT
);

CREATE TABLE IF NOT EXISTS mart.mart_route_card (
    month DATE,
    loading_city_gcid INT,
    unloading_city_gcid INT,
    body_group TEXT,
    weight_category TEXT,
    volume_category TEXT,
    p25_trip NUMERIC, median_trip NUMERIC, p75_trip NUMERIC, avg_trip NUMERIC,
    p25_km NUMERIC, median_km NUMERIC, p75_km NUMERIC,
    trips_count BIGINT, carriers_count BIGINT,
    cv_rate NUMERIC, mom_pct NUMERIC, yoy_pct NUMERIC,
    reliability_level TEXT
);

CREATE TABLE IF NOT EXISTS mart.ml_price_predictions (
    price_id BIGINT,
    loading_date DATE,
    loading_city_gcid INT, unloading_city_gcid INT, body_group TEXT,
    actual_price_rub NUMERIC, predicted_price_rub NUMERIC,
    abs_error_rub NUMERIC, ape_pct NUMERIC,
    model_name TEXT, scored_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (price_id, model_name)
);
