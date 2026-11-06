import os
import logging
from datetime import date
import psycopg

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("ETL")

AS_OF = date.fromisoformat(os.environ.get("AS_OF", "2026-10-26"))
START = date(2025, 1, 1)
END = AS_OF

def get_conn():
    return psycopg.connect(
        host=os.environ["PGHOST"], port=os.environ.get("PGPORT", 5432),
        user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"]
    )

def main():
    log.info("Starting ETL...")
    with get_conn() as conn:
        with conn.transaction():
            cur = conn.cursor()
            
            # Идемпотентность
            cur.execute("DELETE FROM core.prices_clean WHERE loading_date BETWEEN %s AND %s", (START, END))
            cur.execute("DELETE FROM dq.quarantine_prices WHERE quarantined_at::date = CURRENT_DATE")
            
            # Читаем данные + подтягиваем курс ЦБ (строго по nearest_rate_date)
            cur.execute("""
                SELECT p.id, p.loading_date, p.loading_city_gcid, p.unloading_city_gcid,
                       p.distance, p.total_weight, p.total_volume, p.body_type,
                       p.price, p.currency_code, p.price_type, p.is_fact, p.complex,
                       p.outlier_mark, p.organization_id, p.nearest_rate_date,
                       er.value as rate_value
                FROM prices p
                LEFT JOIN exchange_rates er 
                  ON er.num_code = p.currency_code 
                 AND er.setting_date = p.nearest_rate_date
                WHERE p.loading_date BETWEEN %s AND %s
            """, (START, END))
            rows = cur.fetchall()
            log.info(f"Read {len(rows)} rows from source")

            good_rows = []
            bad_rows = []

            for r in rows:
                (pid, ldate, l_city, u_city, dist, wt, vol, b_type, price, curr, p_type, is_f, comp, out_m, org, rate_date, rate_val) = r
                
                reason = None
                if price is None or price <= 0: reason = "PRICE_LE_ZERO"
                elif curr == 643 and price <= 1000: reason = "PRICE_RUB_LE_1000"
                elif dist is None or dist <= 0: reason = "DISTANCE_LE_ZERO"
                elif wt is not None and wt < 0: reason = "WEIGHT_NEG"
                elif vol is not None and vol < 0: reason = "VOLUME_NEG"
                elif l_city is None or u_city is None: reason = "CITY_NOT_FOUND"
                elif curr != 643 and rate_val is None: reason = "RATE_NOT_FOUND"

                if reason:
                    bad_rows.append((pid, reason))
                    continue
                
                # Правильная конвертация
                if curr == 643:
                    price_rub = float(price)
                else:
                    price_rub = float(price) * float(rate_val)
                
                # Категории
                w_cat = "G20T" if wt and wt >= 30 else "FTL" if wt and wt >= 10 else "10T" if wt and wt >= 5 else "5T" if wt and wt >= 2.5 else "L5T" if wt and wt >= 0.5 else "OTH" if wt else None
                v_cat = "FTL" if vol and 0 < vol <= 120 else "OTH" if vol else None
                b_group = "Тент" if b_type in (56,57,58,59,60,61) else "Рефрижератор" if b_type in (4,46,47,48) else "Изотерм" if b_type == 2 else "Борт" if b_type in (1,15) else "Прочие" if b_type else "Не указан"

                good_rows.append((pid, ldate, l_city, u_city, dist, wt, vol, b_group, w_cat, v_cat, price_rub, p_type, is_f, comp, out_m, org))

            log.info(f"Valid: {len(good_rows)}, Quarantine: {len(bad_rows)}")

            if good_rows:
                cur.executemany("""
                    INSERT INTO core.prices_clean 
                    (price_id, loading_date, loading_city_gcid, unloading_city_gcid, distance, total_weight, total_volume, body_group, weight_category, volume_category, price_rub, price_type, is_fact, complex, outlier_mark, organization_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, good_rows)
            
            if bad_rows:
                cur.executemany("INSERT INTO dq.quarantine_prices (price_id, reason_code) VALUES (%s, %s)", bad_rows)

    log.info("ETL completed successfully.")

if __name__ == "__main__":
    main()
