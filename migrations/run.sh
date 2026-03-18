#!/usr/bin/env bash
# migrations/run.sh
# Run every numbered migration in lexical order; stop on first failure.
# Reads connection parameters from docker/.env (relative to repo root).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/docker/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ERROR: ${ENV_FILE} not found" >&2
    exit 1
fi

# Load env vars (ignore lines starting with #, blank lines, and shell arrays)
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${POSTGRES_USER:-planegraph}"
PGPASSWORD="${POSTGRES_PASSWORD}"
PGDATABASE="${POSTGRES_DB:-planegraph}"

export PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE

echo "Connecting to ${PGHOST}:${PGPORT} as ${PGUSER} @ ${PGDATABASE}"

# Wait for Postgres to be ready (up to 30s)
for i in $(seq 1 30); do
    if pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -q; then
        break
    fi
    echo "  waiting for postgres... (${i}/30)"
    sleep 1
done

if ! pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -q; then
    echo "ERROR: postgres not ready after 30s" >&2
    exit 1
fi

# Run migrations in lexical order
MIGRATION_DIR="${SCRIPT_DIR}"
for migration in $(ls "${MIGRATION_DIR}"/*.sql | sort); do
    echo "Applying: $(basename "${migration}")"
    psql -v ON_ERROR_STOP=1 -f "${migration}"
    echo "  OK: $(basename "${migration}")"
done

echo ""
echo "All migrations complete."
