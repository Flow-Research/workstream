wait_for_daemon() {
  local name="$1"
  local attempt
  for ((attempt = 1; attempt <= 45; attempt++)); do
    if docker exec "${name}" docker info >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  printf 'inner Docker daemon did not become ready after 45 attempts: %s\n' "${name}" >&2
  return 1
}
