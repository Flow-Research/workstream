#!/usr/bin/env bash
set -euo pipefail

readonly TEST_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DAEMON_READY="${TEST_SCRIPT_DIR}/daemon_ready.sh"

test_immediate_daemon_readiness() (
  readonly DIND_NAME=ws-pilot00-readiness-success-dind
  # shellcheck source=daemon_ready.sh
  source "${DAEMON_READY}"
  local docker_calls=0
  local sleep_calls=0
  docker() {
    [[ "$*" == "exec ${DIND_NAME} docker info" ]] || return 99
    docker_calls=$((docker_calls + 1))
    return 0
  }
  sleep() {
    sleep_calls=$((sleep_calls + 1))
  }

  wait_for_daemon "${DIND_NAME}"
  [[ "${docker_calls}" == 1 ]]
  [[ "${sleep_calls}" == 0 ]]
)

test_exhausted_daemon_readiness() (
  readonly DIND_NAME=ws-pilot00-readiness-failure-dind
  # shellcheck source=daemon_ready.sh
  source "${DAEMON_READY}"
  local docker_calls=0
  local sleep_calls=0
  docker() {
    [[ "$*" == "exec ${DIND_NAME} docker info" ]] || return 99
    docker_calls=$((docker_calls + 1))
    return 1
  }
  sleep() {
    sleep_calls=$((sleep_calls + 1))
  }

  local diagnostic diagnostic_file
  diagnostic_file="$(mktemp)"
  trap 'rm -f "${diagnostic_file}"' EXIT
  if wait_for_daemon "${DIND_NAME}" 2>"${diagnostic_file}"; then
    echo "expected daemon readiness exhaustion" >&2
    return 1
  fi
  diagnostic="$(cat "${diagnostic_file}")"
  [[ "${diagnostic}" == \
    "inner Docker daemon did not become ready after 45 attempts: ws-pilot00-readiness-failure-dind" ]]
  [[ "${docker_calls}" == 45 ]]
  [[ "${sleep_calls}" == 45 ]]
)

test_immediate_daemon_readiness
test_exhausted_daemon_readiness
echo "probe readiness tests passed"
