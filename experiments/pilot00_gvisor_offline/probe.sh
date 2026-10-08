#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tool-inputs.env
source "${SCRIPT_DIR}/tool-inputs.env"

readonly ACTION="${1:-all}"
readonly RUN_ID="${PILOT00_RUN_ID:-repro}"
[[ "${RUN_ID}" =~ ^[a-z0-9][a-z0-9-]{0,30}$ ]] || {
  echo "PILOT00_RUN_ID must match [a-z0-9][a-z0-9-]{0,30}" >&2
  exit 64
}

readonly PREFIX="ws-pilot00-${RUN_ID}"
readonly DIND_NAME="${PREFIX}-dind"
readonly DIND_VOLUME="${PREFIX}-dind-state"
readonly STATE_DIR="${PILOT00_STATE_DIR:-/tmp/${PREFIX}}"
readonly TOOLS_DIR="${STATE_DIR}/tools"
readonly CACHE_DIR="${STATE_DIR}/cache"
readonly RESULTS_DIR="${STATE_DIR}/results"
readonly DAEMON_CONFIG="${STATE_DIR}/daemon.json"
readonly OWNER_LABEL="org.workstream.pilot00.run=${RUN_ID}"
# shellcheck source=daemon_ready.sh
source "${SCRIPT_DIR}/daemon_ready.sh"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required command: $1" >&2
    exit 69
  }
}

assert_linux_amd64() {
  [[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || {
    echo "this recorded probe supports only Linux x86_64" >&2
    exit 69
  }
}

assert_owned_container() {
  local name="$1"
  [[ "$(docker inspect --format '{{index .Config.Labels "org.workstream.pilot00.run"}}' "${name}")" == "${RUN_ID}" ]]
}

assert_owned_volume() {
  local name="$1"
  [[ "$(docker volume inspect --format '{{index .Labels "org.workstream.pilot00.run"}}' "${name}")" == "${RUN_ID}" ]]
}

ensure_owned_volume() {
  if docker volume inspect "${DIND_VOLUME}" >/dev/null 2>&1; then
    assert_owned_volume "${DIND_VOLUME}" || {
      echo "refusing volume not owned by this probe: ${DIND_VOLUME}" >&2
      exit 73
    }
  else
    docker volume create --label "${OWNER_LABEL}" "${DIND_VOLUME}" >/dev/null
    assert_owned_volume "${DIND_VOLUME}" || {
      echo "refusing volume not owned by this probe: ${DIND_VOLUME}" >&2
      exit 73
    }
  fi
}

prepare_tools() {
  mkdir -p "${TOOLS_DIR}"
  if [[ ! -f "${TOOLS_DIR}/gvisor.tar.zstd" ]]; then
    curl --fail --location --retry 2 --output "${TOOLS_DIR}/gvisor.tar.zstd" "${GVISOR_URL}"
  fi
  printf '%s  %s\n' "${GVISOR_ARCHIVE_SHA512}" "${TOOLS_DIR}/gvisor.tar.zstd" \
    | sha512sum --check
  if [[ ! -x "${TOOLS_DIR}/runsc" ]]; then
    tar --zstd -xf "${TOOLS_DIR}/gvisor.tar.zstd" -C "${TOOLS_DIR}"
  fi
  "${TOOLS_DIR}/runsc" --version | grep -F "${GVISOR_VERSION}" >/dev/null
}

prepare_images_and_cache() {
  docker pull "${DIND_IMAGE}" >/dev/null
  docker pull "${KANIKO_IMAGE}" >/dev/null
  docker pull "${BASE_PLATFORM_IMAGE}" >/dev/null
  [[ "$(docker image inspect "${KANIKO_IMAGE}" --format '{{.Id}}')" == "${KANIKO_IMAGE_ID}" ]]

  if [[ ! -s "${CACHE_DIR}/cache.sha256" ]]; then
    rm -f "${CACHE_DIR}/cache.sha256" "${CACHE_DIR}/cache.sha256.tmp"
    mkdir -p "${CACHE_DIR}/content"
    docker run --rm \
      --name "${PREFIX}-warmer" \
      --label "${OWNER_LABEL}" \
      --mount "type=bind,src=${CACHE_DIR}/content,dst=/cache" \
      --entrypoint /kaniko/warmer \
      "${KANIKO_IMAGE}" \
      --cache-dir=/cache \
      --image="${BASE_PLATFORM_IMAGE}"
    docker run --rm --network none \
      --name "${PREFIX}-cache-readable" \
      --label "${OWNER_LABEL}" \
      --mount "type=bind,src=${CACHE_DIR}/content,dst=/cache" \
      --entrypoint /busybox/sh \
      "${KANIKO_IMAGE}" \
      -ceu 'chmod -R a+rX /cache'
    (
      cd "${CACHE_DIR}/content"
      find . -type f -print0 | sort -z | xargs -0 sha256sum > "${CACHE_DIR}/cache.sha256.tmp"
    )
    mv "${CACHE_DIR}/cache.sha256.tmp" "${CACHE_DIR}/cache.sha256"
    docker run --rm --network none \
      --name "${PREFIX}-cache-seal" \
      --label "${OWNER_LABEL}" \
      --mount "type=bind,src=${CACHE_DIR}/content,dst=/cache" \
      --entrypoint /busybox/sh \
      "${KANIKO_IMAGE}" \
      -ceu 'find /cache -type d -exec chmod 0555 {} \;; find /cache -type f -exec chmod 0444 {} \;'
  fi
  (
    cd "${CACHE_DIR}/content"
    sha256sum --check "${CACHE_DIR}/cache.sha256"
  )
  local platform_digest="${BASE_PLATFORM_IMAGE##*@}"
  [[ -f "${CACHE_DIR}/content/${platform_digest}/blobs/sha256/${platform_digest#sha256:}" ]]
}

write_daemon_config() {
  cat > "${DAEMON_CONFIG}" <<'JSON'
{
  "runtimes": {
    "ws-pilot00-runsc": {
      "path": "/opt/gvisor/runsc",
      "runtimeArgs": [
        "--network=none",
        "--platform=systrap",
        "--host-uds=none",
        "--gvisor-marker-file"
      ]
    }
  },
  "features": {"containerd-snapshotter": false},
  "iptables": false,
  "ip-masq": false,
  "bridge": "none"
}
JSON
}

start_harness() {
  mkdir -p "${RESULTS_DIR}"
  write_daemon_config
  ensure_owned_volume
  if docker inspect "${DIND_NAME}" >/dev/null 2>&1; then
    assert_owned_container "${DIND_NAME}" || {
      echo "refusing container not owned by this probe: ${DIND_NAME}" >&2
      exit 73
    }
    if [[ "$(docker inspect --format '{{.State.Running}}' "${DIND_NAME}")" != true ]]; then
      docker start "${DIND_NAME}" >/dev/null
    fi
  else
    docker run -d \
      --name "${DIND_NAME}" \
      --label "${OWNER_LABEL}" \
      --privileged \
      --network none \
      --cpus 2 \
      --memory 4g \
      --pids-limit 768 \
      -e DOCKER_TLS_CERTDIR= \
      -v "${DIND_VOLUME}:/var/lib/docker" \
      -v "${TOOLS_DIR}:/opt/gvisor:ro" \
      -v "${DAEMON_CONFIG}:/etc/docker/pilot-daemon.json:ro" \
      -v "${SCRIPT_DIR}:/pilot:ro" \
      -v "${STATE_DIR}:/evidence" \
      "${DIND_IMAGE}" \
      --config-file=/etc/docker/pilot-daemon.json >/dev/null
  fi

  wait_for_daemon "${DIND_NAME}"
  docker exec "${DIND_NAME}" docker info --format '{{json .Runtimes}}' \
    | grep -F 'ws-pilot00-runsc' >/dev/null

  if ! docker exec "${DIND_NAME}" docker image inspect "${KANIKO_IMAGE_ID}" >/dev/null 2>&1; then
    docker save "${KANIKO_IMAGE}" | docker exec -i "${DIND_NAME}" docker load >/dev/null
  fi
  docker exec "${DIND_NAME}" docker image inspect "${KANIKO_IMAGE_ID}" >/dev/null
}

inner_docker() {
  docker exec "${DIND_NAME}" docker "$@"
}

create_builder() {
  local name="$1"
  local context="$2"
  local cache_path="$3"
  local output_dir="$4"
  local output_name="$5"
  local destination="$6"
  local memory="$7"
  local output_mount="${8:-bind}"
  local -a output_option
  if [[ "${output_mount}" == tmpfs ]]; then
    output_option=(--tmpfs /out:rw,size=1m,mode=0700)
  else
    output_option=(--mount "type=bind,src=${output_dir},dst=/out")
  fi

  inner_docker create \
    --name "${name}" \
    --runtime ws-pilot00-runsc \
    --network none \
    --user 0:0 \
    --cap-drop ALL \
    --cap-add CHOWN \
    --cap-add DAC_OVERRIDE \
    --cap-add FOWNER \
    --cap-add SYS_CHROOT \
    --security-opt no-new-privileges \
    --pids-limit 128 \
    --memory "${memory}" \
    --cpus 1 \
    --mount type=bind,src=/pilot,dst=/workspace,readonly \
    --mount "type=bind,src=${cache_path},dst=/cache,readonly" \
    "${output_option[@]}" \
    "${KANIKO_IMAGE_ID}" \
    --dockerfile="/workspace/${context}/Dockerfile" \
    --context="dir:///workspace/${context}" \
    --cache=true \
    --cache-dir=/cache \
    --cache-run-layers=false \
    --cache-copy-layers=false \
    --no-push \
    --no-push-cache \
    --tar-path="/out/${output_name}" \
    --destination="${destination}" \
    --force \
    --log-format=text >/dev/null
}

capture_container() {
  local name="$1"
  local result_dir="$2"
  local stem="$3"
  inner_docker inspect "${name}" > "${result_dir}/${stem}-inspect.json"
  inner_docker logs "${name}" > "${result_dir}/${stem}.log" 2>&1 || true
}

capture_builder_boundary() {
  local result_dir="$1"
  inner_docker run --rm \
    --name "${PREFIX}-builder-boundary" \
    --runtime ws-pilot00-runsc \
    --network none \
    --user 0:0 \
    --cap-drop ALL \
    --cap-add CHOWN \
    --cap-add DAC_OVERRIDE \
    --cap-add FOWNER \
    --cap-add SYS_CHROOT \
    --security-opt no-new-privileges \
    --pids-limit 128 \
    --memory 1g \
    --cpus 1 \
    --entrypoint /busybox/sh \
    "${KANIKO_IMAGE_ID}" \
    -ceu '
      test "$(id -u)" -eq 0
      test -e /proc/gvisor/kernel_is_gvisor
      test ! -e /var/run/docker.sock
      capability_mask="$(sed -n "s/^CapEff:[[:space:]]*//p" /proc/self/status)"
      test "$capability_mask" = 000000000004000b
      if wget -T 2 -qO- http://1.1.1.1 >/dev/null 2>&1; then
        exit 71
      fi
      interface_count="$(awk "NR > 2 { count += 1 } END { print count + 0 }" /proc/net/dev)"
      test "$interface_count" -eq 1
      grep -Eq "^[[:space:]]*lo:" /proc/net/dev
      printf "builder_uid=0\nbuilder_cap_eff=%s\nbuilder_network=loopback-only\nbuilder_host_socket=absent\nbuilder_runtime=gvisor\n" "$capability_mask"
    ' > "${result_dir}/builder-boundary.log"
}

run_probe() {
  local evidence_id="${PILOT00_EVIDENCE_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
  [[ "${evidence_id}" =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,47}$ ]] || {
    echo "PILOT00_EVIDENCE_ID must match [A-Za-z0-9][A-Za-z0-9-]{0,47}" >&2
    exit 64
  }
  assert_owned_container "${DIND_NAME}" || {
    echo "run prepare first" >&2
    exit 69
  }
  local host_result_dir="${RESULTS_DIR}/${evidence_id}"
  local inner_result_dir="/evidence/results/${evidence_id}"
  local inner_output_dir="${inner_result_dir}/output"
  mkdir -p "${host_result_dir}"
  docker exec "${DIND_NAME}" mkdir -p "${inner_output_dir}"
  docker exec "${DIND_NAME}" chown 0:0 "${inner_output_dir}"
  docker exec "${DIND_NAME}" chmod 0755 "${inner_output_dir}"

  capture_builder_boundary "${host_result_dir}"

  local build_name="${PREFIX}-build"
  local image_tag="ws-pilot00-sample:${RUN_ID}-${evidence_id,,}"
  create_builder "${build_name}" sample /evidence/cache/content "${inner_output_dir}" sample.tar "${image_tag}" 1g
  inner_docker inspect "${build_name}" > "${host_result_dir}/build-launch.json"
  : > "${host_result_dir}/build-stats.ndjson"
  local build_start_ns build_end_ns build_exit
  build_start_ns="$(date +%s%N)"
  inner_docker start "${build_name}" >/dev/null
  while [[ "$(inner_docker inspect "${build_name}" --format '{{.State.Running}}')" == true ]]; do
    inner_docker stats --no-stream --format '{{json .}}' "${build_name}" \
      >> "${host_result_dir}/build-stats.ndjson" || true
    sleep 0.5
  done
  build_end_ns="$(date +%s%N)"
  build_exit="$(inner_docker inspect "${build_name}" --format '{{.State.ExitCode}}')"
  capture_container "${build_name}" "${host_result_dir}" build
  inner_docker rm -v "${build_name}" >/dev/null
  [[ "${build_exit}" == 0 ]]

  local output_sha output_bytes
  output_sha="$(sha256sum "${host_result_dir}/output/sample.tar" | cut -d' ' -f1)"
  output_bytes="$(stat -c %s "${host_result_dir}/output/sample.tar")"
  inner_docker load -i "${inner_output_dir}/sample.tar" > "${host_result_dir}/image-load.log"

  local oracle_name="${PREFIX}-oracle"
  inner_docker create \
    --name "${oracle_name}" \
    --runtime ws-pilot00-runsc \
    --network none \
    --read-only \
    --user 65532:65532 \
    --cap-drop ALL \
    --security-opt no-new-privileges \
    --pids-limit 32 \
    --memory 256m \
    --cpus 0.5 \
    --mount type=bind,src=/pilot/oracle.sh,dst=/oracle.sh,readonly \
    --entrypoint /oracle.sh \
    "${image_tag}" >/dev/null
  local oracle_start_ns oracle_end_ns oracle_exit
  oracle_start_ns="$(date +%s%N)"
  inner_docker start --attach "${oracle_name}" > "${host_result_dir}/oracle.log" 2>&1 || true
  oracle_end_ns="$(date +%s%N)"
  oracle_exit="$(inner_docker inspect "${oracle_name}" --format '{{.State.ExitCode}}')"
  inner_docker inspect "${oracle_name}" > "${host_result_dir}/oracle-inspect.json"
  inner_docker rm -v "${oracle_name}" >/dev/null
  [[ "${oracle_exit}" == 0 ]]
  grep -Fx 'oracle=pass' "${host_result_dir}/oracle.log" >/dev/null

  local work_name="${PREFIX}-work-failure"
  create_builder "${work_name}" sample-invalid /evidence/cache/content "${inner_output_dir}" invalid.tar "${image_tag}-invalid" 1g
  local work_start_ns work_end_ns
  work_start_ns="$(date +%s%N)"
  inner_docker start --attach "${work_name}" > "${host_result_dir}/work-failure.log" 2>&1 || true
  work_end_ns="$(date +%s%N)"
  local work_exit
  work_exit="$(inner_docker inspect "${work_name}" --format '{{.State.ExitCode}}')"
  capture_container "${work_name}" "${host_result_dir}" work-failure
  inner_docker rm -v "${work_name}" >/dev/null
  [[ "${work_exit}" == 42 ]]
  grep -F 'intentional contributor Dockerfile failure' "${host_result_dir}/work-failure.log" >/dev/null

  docker exec "${DIND_NAME}" mkdir -p /evidence/empty-cache
  docker exec "${DIND_NAME}" chmod 0555 /evidence/empty-cache
  local miss_name="${PREFIX}-cache-miss"
  create_builder "${miss_name}" sample /evidence/empty-cache "${inner_output_dir}" cache-miss.tar "${image_tag}-cache-miss" 1g
  local miss_start_ns miss_end_ns
  miss_start_ns="$(date +%s%N)"
  inner_docker start --attach "${miss_name}" > "${host_result_dir}/cache-miss.log" 2>&1 || true
  miss_end_ns="$(date +%s%N)"
  local miss_exit
  miss_exit="$(inner_docker inspect "${miss_name}" --format '{{.State.ExitCode}}')"
  capture_container "${miss_name}" "${host_result_dir}" cache-miss
  inner_docker rm -v "${miss_name}" >/dev/null
  [[ "${miss_exit}" != 0 ]]
  grep -F 'network is unreachable' "${host_result_dir}/cache-miss.log" >/dev/null

  local timeout_name="${PREFIX}-timeout"
  create_builder "${timeout_name}" sample /evidence/cache/content "${inner_output_dir}" timeout.tar "${image_tag}-timeout" 1g
  local timeout_start_ns timeout_end_ns timeout_running timeout_exit timeout_oom
  timeout_start_ns="$(date +%s%N)"
  inner_docker start "${timeout_name}" >/dev/null
  sleep 5
  timeout_running="$(inner_docker inspect "${timeout_name}" --format '{{.State.Running}}')"
  inner_docker stop --time 1 "${timeout_name}" >/dev/null
  timeout_end_ns="$(date +%s%N)"
  timeout_exit="$(inner_docker inspect "${timeout_name}" --format '{{.State.ExitCode}}')"
  timeout_oom="$(inner_docker inspect "${timeout_name}" --format '{{.State.OOMKilled}}')"
  capture_container "${timeout_name}" "${host_result_dir}" timeout
  inner_docker rm -v "${timeout_name}" >/dev/null
  [[ "${timeout_running}" == true && "${timeout_oom}" == false ]]
  [[ "${timeout_exit}" == 143 || "${timeout_exit}" == 137 ]]

  local memory_name="${PREFIX}-memory"
  create_builder "${memory_name}" sample /evidence/cache/content "${inner_output_dir}" memory.tar "${image_tag}-memory" 16m
  local memory_start_ns memory_end_ns
  memory_start_ns="$(date +%s%N)"
  inner_docker start --attach "${memory_name}" > "${host_result_dir}/memory-limit.log" 2>&1 || true
  memory_end_ns="$(date +%s%N)"
  local memory_exit memory_oom
  memory_exit="$(inner_docker inspect "${memory_name}" --format '{{.State.ExitCode}}')"
  memory_oom="$(inner_docker inspect "${memory_name}" --format '{{.State.OOMKilled}}')"
  capture_container "${memory_name}" "${host_result_dir}" memory-limit
  inner_docker rm -v "${memory_name}" >/dev/null
  [[ "${memory_exit}" == 137 && "${memory_oom}" == true ]]

  local disk_name="${PREFIX}-disk"
  create_builder "${disk_name}" sample /evidence/cache/content /out disk.tar "${image_tag}-disk" 1g tmpfs
  local disk_start_ns disk_end_ns
  disk_start_ns="$(date +%s%N)"
  inner_docker start --attach "${disk_name}" > "${host_result_dir}/disk-limit.log" 2>&1 || true
  disk_end_ns="$(date +%s%N)"
  local disk_exit
  disk_exit="$(inner_docker inspect "${disk_name}" --format '{{.State.ExitCode}}')"
  capture_container "${disk_name}" "${host_result_dir}" disk-limit
  inner_docker rm -v "${disk_name}" >/dev/null
  [[ "${disk_exit}" != 0 ]]
  grep -F 'no space left on device' "${host_result_dir}/disk-limit.log" >/dev/null

  (
    cd "${CACHE_DIR}/content"
    sha256sum --check "${CACHE_DIR}/cache.sha256" > "${host_result_dir}/cache-verification.log"
  )

  BUILD_MS="$(((build_end_ns-build_start_ns)/1000000))" \
  ORACLE_MS="$(((oracle_end_ns-oracle_start_ns)/1000000))" \
  WORK_MS="$(((work_end_ns-work_start_ns)/1000000))" \
  MISS_MS="$(((miss_end_ns-miss_start_ns)/1000000))" \
  TIMEOUT_MS="$(((timeout_end_ns-timeout_start_ns)/1000000))" \
  MEMORY_MS="$(((memory_end_ns-memory_start_ns)/1000000))" \
  DISK_MS="$(((disk_end_ns-disk_start_ns)/1000000))" \
  OUTPUT_SHA="${output_sha}" OUTPUT_BYTES="${output_bytes}" \
  CACHE_BYTES="$(du -sb "${CACHE_DIR}/content" | cut -f1)" \
  TOOLS_BYTES="$(du -sb "${TOOLS_DIR}" | cut -f1)" \
  CACHE_MANIFEST_SHA="$(sha256sum "${CACHE_DIR}/cache.sha256" | cut -d' ' -f1)" \
  DOCKER_VERSION="$(docker version --format '{{.Client.Version}}/{{.Server.Version}}')" \
  DIND_INPUT="${DIND_IMAGE}" KANIKO_INPUT="${KANIKO_IMAGE}" \
  BASE_PLATFORM_INPUT="${BASE_PLATFORM_IMAGE}" GVISOR_INPUT="${GVISOR_VERSION}" \
  STATS_PATH="${host_result_dir}/build-stats.ndjson" \
  WORK_EXIT="${work_exit}" MISS_EXIT="${miss_exit}" \
  TIMEOUT_EXIT="${timeout_exit}" MEMORY_EXIT="${memory_exit}" \
  DISK_EXIT="${disk_exit}" EVIDENCE_ID="${evidence_id}" \
  python3 - "${host_result_dir}/result.json" <<'PY'
import json
import os
import platform
import sys


def size_bytes(value):
    units = {"GiB": 1024**3, "MiB": 1024**2, "KiB": 1024, "B": 1}
    for unit, multiplier in units.items():
        if value.endswith(unit):
            return round(float(value.removesuffix(unit)) * multiplier)
    raise ValueError(value)


stats = []
with open(os.environ["STATS_PATH"], encoding="utf-8") as stream:
    for line in stream:
        if line.strip():
            stats.append(json.loads(line))

result = {
    "schema_version": "pilot00_gvisor_offline_probe_v1",
    "evidence_id": os.environ["EVIDENCE_ID"],
    "host": {"platform": platform.platform(), "machine": platform.machine()},
    "inputs": {
        "docker_client_server": os.environ["DOCKER_VERSION"],
        "gvisor": os.environ["GVISOR_INPUT"],
        "outer_harness_image": os.environ["DIND_INPUT"],
        "builder_image": os.environ["KANIKO_INPUT"],
        "base_platform_manifest": os.environ["BASE_PLATFORM_INPUT"],
        "cache_manifest_sha256": os.environ["CACHE_MANIFEST_SHA"],
    },
    "isolation": {
        "trusted_outer_harness_privileged": True,
        "trusted_outer_harness_network": "none",
        "runtime": "runsc release-20260928.0 systrap",
        "network": "none",
        "host_socket_mounted": False,
        "builder_privileged": False,
        "builder_capabilities": ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SYS_CHROOT"],
        "oracle_uid": 65532,
        "oracle_capabilities": [],
    },
    "limits": {
        "builder_cpu": 1.0,
        "builder_memory_bytes": 1_073_741_824,
        "builder_pids": 128,
        "oracle_cpu": 0.5,
        "oracle_memory_bytes": 268_435_456,
        "oracle_pids": 32,
        "output_disk_failure_bytes": 1_048_576,
    },
    "observed": {
        "build_peak_cpu_percent_of_one_core": max(float(item["CPUPerc"].removesuffix("%")) for item in stats),
        "build_peak_memory_bytes": max(size_bytes(item["MemUsage"].split(" / ", 1)[0]) for item in stats),
        "build_peak_pids": max(int(item["PIDs"]) for item in stats),
        "build_network_io_samples": sorted({item["NetIO"] for item in stats}),
        "sealed_cache_bytes": int(os.environ["CACHE_BYTES"]),
        "gvisor_tools_bytes": int(os.environ["TOOLS_BYTES"]),
    },
    "results": {
        "build": {"outcome": "completed", "elapsed_ms": int(os.environ["BUILD_MS"])},
        "oracle": {"outcome": "passed", "elapsed_ms": int(os.environ["ORACLE_MS"])},
        "dockerfile_failure": {"class": "work_failure", "exit_code": int(os.environ["WORK_EXIT"]), "elapsed_ms": int(os.environ["WORK_MS"])},
        "cache_miss": {"class": "infrastructure_failure", "exit_code": int(os.environ["MISS_EXIT"]), "elapsed_ms": int(os.environ["MISS_MS"])},
        "timeout": {"class": "infrastructure_failure", "exit_code": int(os.environ["TIMEOUT_EXIT"]), "elapsed_ms": int(os.environ["TIMEOUT_MS"])},
        "memory_limit": {"class": "infrastructure_failure", "exit_code": int(os.environ["MEMORY_EXIT"]), "elapsed_ms": int(os.environ["MEMORY_MS"]), "oom_killed": True},
        "disk_limit": {"class": "infrastructure_failure", "exit_code": int(os.environ["DISK_EXIT"]), "elapsed_ms": int(os.environ["DISK_MS"])},
    },
    "output": {
        "tar_sha256": os.environ["OUTPUT_SHA"],
        "tar_bytes": int(os.environ["OUTPUT_BYTES"]),
    },
}
with open(sys.argv[1], "w", encoding="utf-8") as stream:
    json.dump(result, stream, indent=2, sort_keys=True)
    stream.write("\n")
PY
  docker exec "${DIND_NAME}" chmod -R a+rX "${inner_result_dir}"
  cat "${host_result_dir}/result.json"
}

cleanup() {
  if docker inspect "${DIND_NAME}" >/dev/null 2>&1; then
    assert_owned_container "${DIND_NAME}" || {
      echo "refusing container not owned by this probe: ${DIND_NAME}" >&2
      exit 73
    }
    docker stop --time 20 "${DIND_NAME}" >/dev/null
    docker rm "${DIND_NAME}" >/dev/null
  fi
  if docker volume inspect "${DIND_VOLUME}" >/dev/null 2>&1; then
    assert_owned_volume "${DIND_VOLUME}" || {
      echo "refusing volume not owned by this probe: ${DIND_VOLUME}" >&2
      exit 73
    }
    docker volume rm "${DIND_VOLUME}" >/dev/null
  fi
  echo "removed ${PREFIX} Docker resources; retained ${STATE_DIR} evidence"
}

for command in docker curl sha256sum sha512sum tar python3 du stat; do
  require_command "${command}"
done
assert_linux_amd64

case "${ACTION}" in
  prepare)
    prepare_tools
    prepare_images_and_cache
    start_harness
    ;;
  run)
    run_probe
    ;;
  all)
    prepare_tools
    prepare_images_and_cache
    start_harness
    run_probe
    ;;
  cleanup)
    cleanup
    ;;
  *)
    echo "usage: $0 [prepare|run|all|cleanup]" >&2
    exit 64
    ;;
esac
