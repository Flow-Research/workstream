#!/bin/sh
set -eu

sdk_marker=/etc/workstream/project-agent-sdk-environment
if [ ! -f "$sdk_marker" ] || [ -L "$sdk_marker" ] \
    || [ "$(stat -c '%u:%g:%a' -- "$sdk_marker")" != "0:0:444" ]; then
    echo "project agent SDK environment marker is unavailable or unsafe" >&2
    exit 1
fi
sdk_environment="$(cat -- "$sdk_marker")"
case "$sdk_environment" in
    agents|omnicore)
        ;;
    *)
        echo "project agent SDK environment marker is unavailable or unsafe" >&2
        exit 1
        ;;
esac
role="${WORKSTREAM_RELEASE_ROLE:-}"
runtime="${WORKSTREAM_PROJECT_AGENT_RUNTIME:-}"
provider="${WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER:-}"
model_api="${WORKSTREAM_PROJECT_AGENT_MODEL_API:-}"
model="${WORKSTREAM_PROJECT_AGENT_MODEL:-}"
if [ "$role" = "model-proxy" ]; then
    if [ "$sdk_environment" != "agents" ]; then
        echo "model proxy requires the pinned agents SDK environment" >&2
        exit 1
    fi
elif [ "$role" != "parser" ]; then
    case "$runtime:$sdk_environment" in
        openai_agents_sdk:agents|omnicore_agent:omnicore)
            ;;
        manager_authored:agents|manager_authored:omnicore)
            if [ "$provider:$model_api:$model" != "none:none:none" ]; then
                echo "manager-authored project agent configuration is invalid" >&2
                exit 1
            fi
            ;;
        *)
            echo "project agent runtime does not match the installed SDK environment" >&2
            exit 1
            ;;
    esac
    if [ "$runtime" = "omnicore_agent" ] \
        && [ "$provider:$model_api" != "openrouter:chat_completions" ]; then
        echo "OmniCoreAgent requires OpenRouter chat completions" >&2
        exit 1
    fi
fi
unset sdk_marker sdk_environment model_api model

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
unset WORKSTREAM_PROJECT_AGENT_API_KEY
unset OPENAI_API_KEY
unset OPENROUTER_API_KEY
unset WORKSTREAM_GITHUB_APP_PRIVATE_KEY
unset WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID
unset WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY
unset WORKSTREAM_ARTIFACT_S3_SESSION_TOKEN
unset WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET
unset WORKSTREAM_DEV_AUTH_TOKEN
unset WORKSTREAM_TOKEN_INTROSPECTION_CLIENT_SECRET
unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
unset AWS_SESSION_TOKEN
unset AWS_SHARED_CREDENTIALS_FILE
unset AWS_CONFIG_FILE
unset AWS_WEB_IDENTITY_TOKEN_FILE

if [ "$role" != "worker" ] && { [ -n "${WORKSTREAM_GITHUB_APP_ID:-}" ] \
    || [ -n "${WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE:-}" ] \
    || [ -n "${WORKSTREAM_GITHUB_APP_INSTALLATION_ID:-}" ]; }; then
    echo "GitHub App settings require the worker release role" >&2
    exit 1
fi

case "$role" in
    api)
        load_required_secret WORKSTREAM_DATABASE_URL "${WORKSTREAM_DATABASE_URL_FILE:-}"
        load_required_secret WORKSTREAM_CELERY_BROKER_URL "${WORKSTREAM_CELERY_BROKER_URL_FILE:-}"
        load_required_secret WORKSTREAM_API_RATE_LIMIT_KEY_SECRET "${WORKSTREAM_API_RATE_LIMIT_KEY_SECRET_FILE:-}"
        load_required_secret WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET "${WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET_FILE:-}"
        ;;
    worker)
        load_required_secret WORKSTREAM_DATABASE_URL "${WORKSTREAM_DATABASE_URL_FILE:-}"
        load_required_secret WORKSTREAM_CELERY_BROKER_URL "${WORKSTREAM_CELERY_BROKER_URL_FILE:-}"
        if [ -n "${WORKSTREAM_GITHUB_APP_ID:-}${WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE:-}${WORKSTREAM_GITHUB_APP_INSTALLATION_ID:-}" ]; then
            if [ -z "${WORKSTREAM_GITHUB_APP_ID:-}" ] || [ -z "${WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE:-}" ]; then
                echo "GitHub App requires paired App ID and private key file" >&2
                exit 1
            fi
            for github_identity in "$WORKSTREAM_GITHUB_APP_ID" "${WORKSTREAM_GITHUB_APP_INSTALLATION_ID:-1}"; do
                case "$github_identity" in
                    *[!0-9]*|"")
                        echo "GitHub App identity must be a positive integer" >&2
                        exit 1
                        ;;
                esac
                case "$github_identity" in
                    *[1-9]*) ;;
                    *)
                        echo "GitHub App identity must be a positive integer" >&2
                        exit 1
                        ;;
                esac
            done
            unset github_identity
            load_required_secret WORKSTREAM_GITHUB_APP_PRIVATE_KEY "${WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE}"
        fi
        ;;
    model-proxy)
        load_required_secret WORKSTREAM_DATABASE_URL "${WORKSTREAM_DATABASE_URL_FILE:-}"
        openai_key_file="${WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE:-}"
        openrouter_key_file="${WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE:-}"
        if [ "$runtime" = "manager_authored" ]; then
            if [ -z "$openai_key_file" ] && [ -z "$openrouter_key_file" ]; then
                echo "enabled model proxy requires at least one provider credential" >&2
                exit 1
            fi
        else
            case "$provider" in
                openai)
                    if [ -z "$openai_key_file" ]; then
                        echo "inference setup requires its selected provider credential" >&2
                        exit 1
                    fi
                    ;;
                openrouter)
                    if [ -z "$openrouter_key_file" ]; then
                        echo "inference setup requires its selected provider credential" >&2
                        exit 1
                    fi
                    ;;
                *)
                    echo "project agent model provider is unsupported" >&2
                    exit 1
                    ;;
            esac
        fi
        if [ -n "$openai_key_file" ]; then
            load_required_secret OPENAI_API_KEY "$openai_key_file"
        fi
        if [ -n "$openrouter_key_file" ]; then
            load_required_secret OPENROUTER_API_KEY "$openrouter_key_file"
        fi
        unset openai_key_file openrouter_key_file
        ;;
    beat)
        load_required_secret WORKSTREAM_DATABASE_URL "${WORKSTREAM_DATABASE_URL_FILE:-}"
        load_required_secret WORKSTREAM_CELERY_BROKER_URL "${WORKSTREAM_CELERY_BROKER_URL_FILE:-}"
        ;;
    proof)
        load_required_secret WORKSTREAM_DATABASE_URL "${WORKSTREAM_DATABASE_URL_FILE:-}"
        ;;
    parser)
        unset WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_CERTIFICATE_FILE
        unset WORKSTREAM_ARTIFACT_S3_ROLES_ANYWHERE_PRIVATE_KEY_FILE
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
unset WORKSTREAM_MODEL_PROXY_OPENAI_API_KEY_FILE
unset WORKSTREAM_MODEL_PROXY_OPENROUTER_API_KEY_FILE
unset WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE
if [ -z "${WORKSTREAM_GITHUB_APP_ID:-}" ]; then
    unset WORKSTREAM_GITHUB_APP_ID
fi
if [ -z "${WORKSTREAM_GITHUB_APP_INSTALLATION_ID:-}" ]; then
    unset WORKSTREAM_GITHUB_APP_INSTALLATION_ID
fi
unset OPENAI_API_KEY_FILE
unset AWS_SHARED_CREDENTIALS_FILE
unset AWS_CONFIG_FILE
unset AWS_WEB_IDENTITY_TOKEN_FILE
unset WORKSTREAM_RELEASE_ROLE
unset role runtime provider

exec "$@"
