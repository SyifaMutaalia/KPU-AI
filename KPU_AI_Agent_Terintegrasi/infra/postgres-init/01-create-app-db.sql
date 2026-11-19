\getenv app_db_name APP_DB_NAME
\getenv app_db_user APP_DB_USER
\getenv app_db_password APP_DB_PASSWORD

SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'app_db_user', :'app_db_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_db_user')
\gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'app_db_name', :'app_db_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_db_name')
\gexec
