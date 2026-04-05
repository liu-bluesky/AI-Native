#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$SCRIPT_DIR/compose.prod.yml}"
ENV_FILE="${ENV_FILE:-$SCRIPT_DIR/.env.prod}"
BACKUP_DIR="${BACKUP_DIR:-$SCRIPT_DIR/backup}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ai-employee-postgres}"
SKILL_VOLUME="${SKILL_VOLUME:-ai_employee_mcp_skills_knowledge_prod}"
API_DATA_VOLUME="${API_DATA_VOLUME:-ai_employee_api_data_prod}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found" >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "compose file not found: $COMPOSE_FILE" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "env file not found: $ENV_FILE" >&2
  echo "copy docker/.env.prod.example to docker/.env.prod first" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

require_service_container() {
  local container_name="$1"
  if ! docker ps --format '{{.Names}}' | grep -qx "$container_name"; then
    echo "container not running: $container_name" >&2
    exit 1
  fi
}

usage() {
  cat <<'EOF'
Usage:
  ./deploy.sh pull
  ./deploy.sh up
  ./deploy.sh deploy
  ./deploy.sh ps
  ./deploy.sh logs [service]
  ./deploy.sh backup-db [output.sql]
  ./deploy.sh restore-db <input.sql>
  ./deploy.sh backup-skill-volume [target_dir]
  ./deploy.sh restore-skill-volume [source_dir]
  ./deploy.sh backup-api-data-volume [target_dir]
  ./deploy.sh restore-api-data-volume [source_dir]

Environment overrides:
  ENV_FILE=/path/to/.env.prod
  COMPOSE_FILE=/path/to/compose.prod.yml
  BACKUP_DIR=/path/to/backup
  POSTGRES_CONTAINER=custom-postgres-container
  SKILL_VOLUME=custom_skill_volume
  API_DATA_VOLUME=custom_api_data_volume
EOF
}

ACTION="${1:-}"
if [[ -z "$ACTION" ]]; then
  usage
  exit 1
fi
shift || true

case "$ACTION" in
  pull)
    compose pull
    ;;
  up)
    compose up -d
    ;;
  deploy)
    compose pull
    compose up -d
    ;;
  ps)
    compose ps
    ;;
  logs)
    compose logs -f "${1:-}"
    ;;
  backup-db)
    require_service_container "$POSTGRES_CONTAINER"
    output_file="${1:-$BACKUP_DIR/ai_employee.sql}"
    mkdir -p "$(dirname "$output_file")"
    db_user="$(grep '^DB_USER=' "$ENV_FILE" | head -n1 | cut -d= -f2- || true)"
    db_name="$(grep '^DB_NAME=' "$ENV_FILE" | head -n1 | cut -d= -f2- || true)"
    db_user="${db_user:-admin}"
    db_name="${db_name:-ai_employee}"
    docker exec "$POSTGRES_CONTAINER" pg_dump -U "$db_user" "$db_name" >"$output_file"
    echo "db backup written to $output_file"
    ;;
  restore-db)
    require_service_container "$POSTGRES_CONTAINER"
    input_file="${1:-}"
    if [[ -z "$input_file" || ! -f "$input_file" ]]; then
      echo "restore-db requires an existing sql file" >&2
      exit 1
    fi
    db_user="$(grep '^DB_USER=' "$ENV_FILE" | head -n1 | cut -d= -f2- || true)"
    db_name="$(grep '^DB_NAME=' "$ENV_FILE" | head -n1 | cut -d= -f2- || true)"
    db_user="${db_user:-admin}"
    db_name="${db_name:-ai_employee}"
    cat "$input_file" | docker exec -i "$POSTGRES_CONTAINER" psql -U "$db_user" -d "$db_name"
    echo "db restored from $input_file"
    ;;
  backup-skill-volume)
    target_dir="${1:-$BACKUP_DIR/mcp-skills-knowledge}"
    mkdir -p "$target_dir"
    docker run --rm \
      -v "$SKILL_VOLUME:/from" \
      -v "$target_dir:/to" \
      alpine sh -c 'cp -a /from/. /to/'
    echo "skill volume backed up to $target_dir"
    ;;
  restore-skill-volume)
    source_dir="${1:-$BACKUP_DIR/mcp-skills-knowledge}"
    if [[ ! -d "$source_dir" ]]; then
      echo "source dir not found: $source_dir" >&2
      exit 1
    fi
    docker run --rm \
      -v "$SKILL_VOLUME:/to" \
      -v "$source_dir:/from" \
      alpine sh -c 'cp -a /from/. /to/'
    echo "skill volume restored from $source_dir"
    ;;
  backup-api-data-volume)
    target_dir="${1:-$BACKUP_DIR/api-data}"
    mkdir -p "$target_dir"
    docker run --rm \
      -v "$API_DATA_VOLUME:/from" \
      -v "$target_dir:/to" \
      alpine sh -c 'cp -a /from/. /to/'
    echo "api data volume backed up to $target_dir"
    ;;
  restore-api-data-volume)
    source_dir="${1:-$BACKUP_DIR/api-data}"
    if [[ ! -d "$source_dir" ]]; then
      echo "source dir not found: $source_dir" >&2
      exit 1
    fi
    docker run --rm \
      -v "$API_DATA_VOLUME:/to" \
      -v "$source_dir:/from" \
      alpine sh -c 'cp -a /from/. /to/'
    echo "api data volume restored from $source_dir"
    ;;
  *)
    usage
    exit 1
    ;;
esac
