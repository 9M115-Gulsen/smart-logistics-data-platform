#!/bin/bash
set -e

echo "Waiting for Postgres to finish initialization (this takes ~30s)..."
sleep 30

export PGPASSWORD=$POSTGRES_PASSWORD
until psql -h $PGHOST -U $POSTGRES_USER -d $POSTGRES_DB -c '\q' 2>/dev/null; do
  echo "Postgres is still restarting, waiting..."
  sleep 2
done
echo "Postgres is ready!"

echo "Running ETL (Stage 1)..."
python -m etl.run_etl

echo "Building Marts (Stage 2)..."
psql -h $PGHOST -U $POSTGRES_USER -d $POSTGRES_DB -f sql/30_mart_route_card.sql

echo "Running ML Training & Inference (Stage 3)..."
python -m ml.train

echo "Pipeline completed successfully!"
