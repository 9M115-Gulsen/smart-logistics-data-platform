import os
import logging
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from catboost import CatBoostRegressor, Pool
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error, mean_absolute_percentage_error

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("ML")

DB_URL = f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}@{os.environ['PGHOST']}:{os.environ['PGPORT']}/{os.environ['POSTGRES_DB']}"
engine = create_engine(DB_URL)

def extract_data():
    query = """
        WITH unique_cities AS (
            SELECT DISTINCT ON (gc_id) gc_id, full_name_local 
            FROM cities 
            ORDER BY gc_id, id
        )
        SELECT pc.price_id, pc.loading_date, pc.distance, pc.total_weight, pc.total_volume,
               pc.body_group, pc.weight_category, pc.price_rub,
               c1.full_name_local as origin_city, c2.full_name_local as dest_city
        FROM core.prices_clean pc
        JOIN unique_cities c1 ON c1.gc_id = pc.loading_city_gcid
        JOIN unique_cities c2 ON c2.gc_id = pc.unloading_city_gcid
        WHERE pc.is_fact = true AND pc.complex = false AND pc.distance > 0
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    log.info(f"Extracted {len(df)} rows for ML")
    return df

def build_features(df):
    df = df.copy()
    
    def get_region(x):
        if pd.isna(x): return 'Unknown'
        parts = str(x).split(',')
        return parts[1].strip() if len(parts) > 1 else 'Unknown'
        
    df['origin_region'] = df['origin_city'].apply(get_region)
    df['dest_region'] = df['dest_city'].apply(get_region)
    
    cat_cols = ['origin_region', 'dest_region', 'body_group', 'weight_category']
    for col in cat_cols:
        df[col] = df[col].fillna('Не указан').astype(str)
    
    d = pd.to_datetime(df['loading_date'])
    df['year'] = d.dt.year
    df['month'] = d.dt.month
    df['dow'] = d.dt.day_of_week
    df['doy'] = d.dt.day_of_year
    
    df['doy_sin'] = np.sin(2 * np.pi * df['doy'] / 365.25)
    df['doy_cos'] = np.cos(2 * np.pi * df['doy'] / 365.25)
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12.0)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12.0)
    df['dow_sin'] = np.sin(2 * np.pi * df['dow'] / 7.0)
    df['dow_cos'] = np.cos(2 * np.pi * df['dow'] / 7.0)
    
    return df

def main():
    log.info("Starting ML pipeline...")
    df = extract_data()
    
    df['loading_date'] = pd.to_datetime(df['loading_date'])
    
    # Разделяем на историю (где есть факт) и будущее (где факта нет)
    hist_mask = df['price_rub'] > 0
    future_mask = df['loading_date'] > '2026-10-26'
    
    hist_df = df[hist_mask].copy()
    future_df = df[future_mask].copy()
    
    train_mask = (hist_df['loading_date'] >= '2026-07-26') & (hist_df['loading_date'] < '2026-10-05')
    test_mask = (hist_df['loading_date'] >= '2026-10-05') & (hist_df['loading_date'] <= '2026-10-26')
    
    train_df = hist_df[train_mask].copy()
    test_df = hist_df[test_mask].copy()
    log.info(f"Train size: {len(train_df)}, Test size: {len(test_df)}, Future for scoring: {len(future_df)}")

    train_feat = build_features(train_df)
    test_feat = build_features(test_df)
    future_feat = build_features(future_df)

    drop_cols = ['price_id', 'loading_date', 'origin_city', 'dest_city', 'price_rub']
    X_train = train_feat.drop(columns=drop_cols)
    y_train = train_feat['price_rub']
    
    X_test = test_feat[X_train.columns]
    y_test = test_feat['price_rub']

    cat_features = ['origin_region', 'dest_region', 'body_group', 'weight_category']

    log.info("Training CatBoostRegressor on log1p(target)...")
    model = CatBoostRegressor(
        iterations=800, 
        learning_rate=0.05, 
        depth=6, 
        random_seed=42, 
        verbose=200,
        cat_features=cat_features
    )
    
    # Логарифмируем таргет для сглаживания выбросов
    train_pool = Pool(X_train, np.log1p(y_train), cat_features=cat_features)
    test_pool = Pool(X_test, np.log1p(y_test), cat_features=cat_features)
    
    model.fit(train_pool, eval_set=test_pool)

    log.info("Evaluating...")
    # Предсказание и обратное преобразование
    preds_log = model.predict(X_test)
    preds = np.expm1(preds_log)
    
    r2 = r2_score(y_test, preds)
    mae = mean_absolute_error(y_test, preds)
    rmse = np.sqrt(mean_squared_error(y_test, preds))
    mape = mean_absolute_percentage_error(y_test, preds) * 100

    log.info(f"=== METRICS ===")
    log.info(f"R2:   {r2:.4f}")
    log.info(f"MAPE: {mape:.2f}%")
    log.info(f"RMSE: {rmse:.2f} RUB")
    log.info(f"MAE:  {mae:.2f} RUB")
    log.info(f"===============")

    log.info("Scoring test set and future requests...")
    
    # 1. Готовим прогнозы для ТЕСТА
    test_df['predicted_price_rub'] = preds
    test_df['actual_price_rub'] = y_test
    test_df['abs_error_rub'] = abs(test_df['actual_price_rub'] - test_df['predicted_price_rub'])
    test_df['ape_pct'] = (test_df['abs_error_rub'] / test_df['actual_price_rub']) * 100
    test_df['model_name'] = 'CatBoost_v2'
    
    # 2. Готовим прогнозы для БУДУЩИХ заявок (actual = NULL)
    if len(future_df) > 0:
        X_future = future_feat[X_train.columns]
        future_preds = np.expm1(model.predict(X_future))
        
        future_df['predicted_price_rub'] = future_preds
        future_df['actual_price_rub'] = np.nan # Строго NULL!
        future_df['abs_error_rub'] = np.nan
        future_df['ape_pct'] = np.nan
        future_df['model_name'] = 'CatBoost_v2'
    
    out_cols = ['price_id', 'loading_date', 'actual_price_rub', 'predicted_price_rub', 'abs_error_rub', 'ape_pct', 'model_name']
    all_preds = pd.concat([test_df[out_cols], future_df[out_cols] if len(future_df) > 0 else pd.DataFrame()])
    
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM mart.ml_price_predictions WHERE model_name = 'CatBoost_v2'"))
        all_preds.to_sql('ml_price_predictions', conn, schema='mart', if_exists='append', index=False)
        
    log.info("ML completed and predictions saved.")

if __name__ == "__main__":
    main()
