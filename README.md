cat << 'EOF' > README.md
# Smart Logistics Data & ML Platform

Прототип аналитической платформы и ML-прогнозирования тарифов грузоперевозок.

## Архитектура
Проект реализован в виде сквозного пайплайна (ETL -> DWH -> ML):
1. **ETL (Python):** Очистка данных, DQ-карантин, конвертация валют по `nearest_rate_date`, обогащение категорий. Реализована идемпотентность (DELETE + INSERT).
2. **DWH (SQL):** Витрина `mart.mart_route_card` с расчетом P25/P50/P75, MoM/YoY и уровнями доверия (HIGH/MEDIUM/LOW_DATA).
3. **ML (Python):** Обучение CatBoostRegressor на логарифмированном таргете, циклическое кодирование дат, строгий Time-Based Split. Batch Inference пишет прогнозы в `mart.ml_price_predictions`.

## Запуск
Всё разворачивается одной командой:
```bash
docker compose up