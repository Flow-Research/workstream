#!/bin/sh
set -eu

load_required_secret() {
    setting_name="$1"
    secret_path="$2"
    if [ -z "$secret_path" ] || [ ! -f "$secret_path" ] || [ -L "$secret_path" ] || [ ! -s "$secret_path" ]; then
        echo "required secret file is unavailable: ${setting_name}" >&2
        exit 1
    fi
    expected_identity="$(id -u):$(id -g):400"
    if [ "$(stat -c '%u:%g:%a' -- "$secret_path")" != "$expected_identity" ]; then
        echo "required secret file has unsafe ownership or mode: ${setting_name}" >&2
        exit 1
    fi
    secret_value="$(cat -- "$secret_path")"
    if [ -z "$secret_value" ]; then
        echo "required secret file is empty: ${setting_name}" >&2
        exit 1
    fi
    export "${setting_name}=${secret_value}"
    unset secret_value
    unset expected_identity
}

unset WORKSTREAM_DATABASE_URL
unset WORKSTREAM_CELERY_BROKER_URL
unset WORKSTREAM_API_RATE_LIMIT_KEY_SECRET
unset WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET
unset OPENAI_API_KEY

case "${WORKSTREAM_RELEASE_ROLE:-}" in
    api)
        load_required_secret WORKSTREAM_DATABASE_URL "${WORKSTREAM_DATABASE_URL_FILE:-}"
        load_required_secret WORKSTREAM_CELERY_BROKER_URL "${WORKSTREAM_CELERY_BROKER_URL_FILE:-}"
        load_required_secret WORKSTREAM_API_RATE_LIMIT_KEY_SECRET "${WORKSTREAM_API_RATE_LIMIT_KEY_SECRET_FILE:-}"
        load_required_secret WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET "${WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET_FILE:-}"
        ;;
    worker)
        load_required_secret WORKSTREAM_DATABASE_URL "${WORKSTREAM_DATABASE_URL_FILE:-}"
        load_required_secret WORKSTREAM_CELERY_BROKER_URL "${WORKSTREAM_CELERY_BROKER_URL_FILE:-}"
        load_required_secret OPENAI_API_KEY "${OPENAI_API_KEY_FILE:-}"
        ;;
    beat)
        load_required_secret WORKSTREAM_CELERY_BROKER_URL "${WORKSTREAM_CELERY_BROKER_URL_FILE:-}"
        ;;
    *)
        echo "required release role is unavailable or unsupported" >&2
        exit 1
        ;;
esac

unset WORKSTREAM_DATABASE_URL_FILE
unset WORKSTREAM_CELERY_BROKER_URL_FILE
unset WORKSTREAM_API_RATE_LIMIT_KEY_SECRET_FILE
unset WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET_FILE
unset OPENAI_API_KEY_FILE
unset WORKSTREAM_RELEASE_ROLE

exec "$@"
