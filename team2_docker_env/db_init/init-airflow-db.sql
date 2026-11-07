-- The default POSTGRES_DB (dsp_app) is created automatically by the postgres
-- image. Airflow needs its own metadata database in the same instance.
CREATE DATABASE airflow;
