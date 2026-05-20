-- harmoni PostgreSQL initialization
-- Creates the airflow database alongside the main harmoni database.
-- Runs automatically on first docker-compose up via docker-entrypoint-initdb.d/

CREATE DATABASE airflow;
GRANT ALL PRIVILEGES ON DATABASE airflow TO harmoni;
