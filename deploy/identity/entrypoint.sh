#!/usr/bin/env bash
# Only configuration/secret loading; authentication remains stock Keycloak.
set -euo pipefail
set +x
if [[ -z "${KC_DB_PASSWORD_FILE:-}" || ! -f "$KC_DB_PASSWORD_FILE" || ! -r "$KC_DB_PASSWORD_FILE" ]]; then
  echo 'Keycloak database password file is required' >&2
  exit 1
fi
if [[ -n "${KC_DB_PASSWORD:-}" ]]; then
  echo 'Use the database password file, not an ambient password' >&2
  exit 1
fi
KC_DB_PASSWORD=$(<"$KC_DB_PASSWORD_FILE")
if [[ -z "$KC_DB_PASSWORD" || "$KC_DB_PASSWORD" == *$'\n'* || "$KC_DB_PASSWORD" == *$'\r'* ]]; then
  echo 'Keycloak database password file is invalid' >&2
  exit 1
fi
export KC_DB_PASSWORD
unset KC_DB_PASSWORD_FILE
# This file is supplied only during explicit initial administration setup.
if [[ -n "${KC_BOOTSTRAP_ADMIN_PASSWORD_FILE:-}" ]]; then
  if [[ -n "${KC_BOOTSTRAP_ADMIN_PASSWORD:-}" || ! -r "$KC_BOOTSTRAP_ADMIN_PASSWORD_FILE" ]]; then
    echo 'Keycloak bootstrap password configuration is invalid' >&2
    exit 1
  fi
  KC_BOOTSTRAP_ADMIN_PASSWORD=$(<"$KC_BOOTSTRAP_ADMIN_PASSWORD_FILE")
  if [[ -z "$KC_BOOTSTRAP_ADMIN_PASSWORD" || "$KC_BOOTSTRAP_ADMIN_PASSWORD" == *$'\n'* || "$KC_BOOTSTRAP_ADMIN_PASSWORD" == *$'\r'* ]]; then
    echo 'Keycloak bootstrap password file is invalid' >&2
    exit 1
  fi
  export KC_BOOTSTRAP_ADMIN_PASSWORD
  unset KC_BOOTSTRAP_ADMIN_PASSWORD_FILE
elif [[ -n "${KC_BOOTSTRAP_ADMIN_PASSWORD:-}" ]]; then
  echo 'Use the explicit bootstrap password file' >&2
  exit 1
fi
exec /opt/keycloak/bin/kc.sh "$@"
