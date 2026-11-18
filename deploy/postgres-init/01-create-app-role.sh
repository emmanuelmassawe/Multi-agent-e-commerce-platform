#!/bin/sh
set -eu

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=app_user="$CLOS_APP_USER" \
  --set=app_password="$CLOS_APP_PASSWORD" \
  --set=ON_ERROR_STOP=1 <<'SQL'
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password' NOSUPERUSER NOBYPASSRLS;
GRANT CONNECT ON DATABASE clos TO :"app_user";
SQL

