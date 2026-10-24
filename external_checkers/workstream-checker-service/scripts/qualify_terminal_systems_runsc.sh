#!/usr/bin/env bash
set -euo pipefail

# Explicit qualification runner for the production service + project image +
# generic trial engine. This mutates only the named, stopped PILOT-00 DIND
# harness and restores its daemon configuration byte-for-byte on every exit.

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
readonly STATE_ROOT="${WORKSTREAM_TS_RUNSC_STATE_ROOT:?set the prepared PILOT-00 state root}"
readonly SHARED_ROOT="${WORKSTREAM_TS_RUNSC_SHARED_ROOT:?set the daemon-visible qualification root}"
readonly CONTAINER="${WORKSTREAM_TS_RUNSC_CONTAINER:?set the owned DIND container}"
readonly PREPARED_CONTAINER="${WORKSTREAM_TS_RUNSC_PREPARED_CONTAINER:?set the stopped prepared DIND container}"
readonly RUN_ID="${WORKSTREAM_TS_RUNSC_RUN_ID:?set the prepared PILOT-00 run ID}"
readonly CHECKER_IMAGE="${WORKSTREAM_TS_RUNSC_CHECKER_IMAGE:-ws-terminal-systems-post:qualification}"
readonly REGISTRY_IMAGE="${WORKSTREAM_TS_RUNSC_REGISTRY_IMAGE:-registry:2}"
readonly INNER_ROOT="/workstream-state"
# Host AF_UNIX paths must stay below 108 bytes even in a deep checkout.
readonly SOCKET_ROOT="$(mktemp -d /tmp/ws493-sockets.XXXXXX)"
readonly INNER_SOCKET_ROOT="/workstream-sockets"
readonly COMPOSITION_ROOT="${SHARED_ROOT}/terminal-systems-runsc-composition"
readonly INNER_COMPOSITION_ROOT="${INNER_ROOT}/terminal-systems-runsc-composition"
readonly ORIGINAL_CONFIG="$(mktemp /tmp/ws493-runsc-daemon.XXXXXX.json)"
ORIGINAL_CONFIG_MODE=""
readonly BUILD_MESSAGES="$(mktemp /tmp/ws493-runsc-build.XXXXXX.jsonl)"
readonly LAUNCHER_MESSAGES="$(mktemp /tmp/ws493-runsc-launcher-build.XXXXXX.jsonl)"
readonly LAUNCHER_PROGRAM_HEADERS="$(mktemp /tmp/ws493-runsc-launcher.XXXXXX.phdr)"
readonly LAUNCHER_DYNAMIC="$(mktemp /tmp/ws493-runsc-launcher.XXXXXX.dynamic)"
readonly METADATA="${WORKSTREAM_TS_RUNSC_METADATA:-/tmp/ws493-terminal-systems-runsc.json}"
readonly RESULT_LOG="${WORKSTREAM_TS_RUNSC_LOG:-/tmp/ws493-terminal-systems-runsc.log}"
readonly EXIT_SIDECAR="${WORKSTREAM_TS_RUNSC_EXIT:-/tmp/ws493-terminal-systems-runsc.exit}"
readonly EXTRACT_CONTAINER="ws493-runsc-registry-extract-${RUN_ID}"
readonly CLEANER_CONTAINER="ws493-runsc-workspace-clean-${RUN_ID}"

STARTED=0
CONFIG_REPLACED=0
EXTRACT_CREATED=0
HOST_CHECKER_BUILT=0
QUALIFIER_CONTAINER_OWNED=0

cleanup_docker() {
  timeout --kill-after=5s 30s docker "$@"
}

remove_composition_root() {
  if cleanup_docker inspect "${CLEANER_CONTAINER}" >/dev/null 2>&1; then
    [[ "$(cleanup_docker inspect --format '{{index .Config.Labels "workstream.qualifier"}}' "${CLEANER_CONTAINER}")" == "terminal-systems-runsc" ]] || return 1
    [[ "$(cleanup_docker inspect --format '{{index .Config.Labels "org.workstream.pilot00.run"}}' "${CLEANER_CONTAINER}")" == "${RUN_ID}" ]] || return 1
    local expected_image
    expected_image="$(cleanup_docker image inspect --format '{{.Id}}' "${PREPARED_IMAGE}")" || return 1
    [[ -n "${expected_image}" && "$(cleanup_docker inspect --format '{{.Image}}' "${CLEANER_CONTAINER}")" == "${expected_image}" ]] || return 1
    cleanup_docker rm -f "${CLEANER_CONTAINER}" >/dev/null || return 1
  fi
  cleanup_docker run --rm \
    --name "${CLEANER_CONTAINER}" \
    --label "org.workstream.pilot00.run=${RUN_ID}" \
    --label "workstream.qualifier=terminal-systems-runsc" \
    --network none \
    --read-only \
    --cap-drop ALL \
    --cap-add DAC_OVERRIDE \
    --security-opt no-new-privileges \
    --pids-limit 16 \
    --memory 67108864 \
    --mount "type=bind,src=${SHARED_ROOT},dst=${INNER_ROOT}" \
    --entrypoint sh \
    "${PREPARED_IMAGE}" -ceu \
    'rm -rf /workstream-state/terminal-systems-runsc-composition' || return 1
  [[ ! -e "${COMPOSITION_ROOT}" ]]
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  set +e
  if [[ "${STARTED}" == 1 ]]; then
    cleanup_docker exec "${CONTAINER}" sh -ceu '
      composition_root="$1"
      if test -s "${composition_root}/registry.pid"; then
        kill "$(cat "${composition_root}/registry.pid")" 2>/dev/null || true
      fi
      docker container ls -aq --filter label=workstream.external-checker=true | xargs -r docker rm -f >/dev/null
      docker container ls -aq --filter label=workstream.trial.deployment-owner=terminal-systems-runsc-qualification | xargs -r docker rm -f >/dev/null
      docker images --format "{{.Repository}}:{{.Tag}}" --filter reference="workstream-trial:*" \
        | xargs -r docker image rm >/dev/null
    ' sh "${INNER_COMPOSITION_ROOT}" || status=1
    cleanup_docker exec "${CONTAINER}" docker image rm \
      127.0.0.1:5000/terminal-systems-post:qualification \
      "${CHECKER_IMAGE}" \
      >/dev/null 2>&1 || status=1
    if [[ -n "${WORKSTREAM_TS_RUNSC_CHECKER_DIGEST:-}" ]]; then
      cleanup_docker exec "${CONTAINER}" docker image rm \
        "127.0.0.1:5000/terminal-systems-post@${WORKSTREAM_TS_RUNSC_CHECKER_DIGEST}" \
        >/dev/null 2>&1 || true
    fi
    cleanup_docker stop --time 15 "${CONTAINER}" >/dev/null 2>&1 || status=1
  fi
  if [[ "${QUALIFIER_CONTAINER_OWNED}" == 1 ]]; then
    cleanup_docker rm "${CONTAINER}" >/dev/null 2>&1 || status=1
  fi
  if [[ "${EXTRACT_CREATED}" == 1 ]]; then
    cleanup_docker rm -f "${EXTRACT_CONTAINER}" >/dev/null 2>&1 || status=1
  fi
  if [[ "${HOST_CHECKER_BUILT}" == 1 ]]; then
    cleanup_docker image rm "${CHECKER_IMAGE}" >/dev/null 2>&1 || status=1
  fi
  if [[ "${CONFIG_REPLACED}" == 1 ]]; then
    cp -- "${ORIGINAL_CONFIG}" "${SHARED_ROOT}/daemon.json" || status=1
    chmod "${ORIGINAL_CONFIG_MODE}" "${SHARED_ROOT}/daemon.json" || status=1
    if ! cmp -s -- "${ORIGINAL_CONFIG}" "${SHARED_ROOT}/daemon.json"; then
      status=1
    fi
  fi
  if [[ -n "${PREPARED_IMAGE:-}" ]]; then
    remove_composition_root || status=1
  fi
  rm -f -- "${ORIGINAL_CONFIG}" "${BUILD_MESSAGES}" "${LAUNCHER_MESSAGES}" \
    "${LAUNCHER_PROGRAM_HEADERS}" "${LAUNCHER_DYNAMIC}"
  # This unique private root is created by this invocation and contains only
  # the trusted service/proxy sockets, never submitted material.
  rm -rf -- "${SOCKET_ROOT}" || status=1
  printf '%s\n' "${status}" >"${EXIT_SIDECAR}"
  exit "${status}"
}
trap cleanup EXIT INT TERM

[[ "${STATE_ROOT}" == /* ]]
[[ "${STATE_ROOT}" =~ ^/tmp/ws-pilot00-[a-z0-9-]+$ ]]
[[ "${SHARED_ROOT}" == "${REPOSITORY_ROOT}/external_checkers/target/ws493-"* ]]
[[ "${CONTAINER}" != "${PREPARED_CONTAINER}" ]]
[[ "${RUN_ID}" =~ ^[a-z0-9][a-z0-9-]{0,30}$ ]]
[[ "${CONTAINER}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]]
[[ "${WORKSTREAM_TS_RUNSC_PREFLIGHT_ONLY:-0}" =~ ^[01]$ ]]
[[ -n "${WORKSTREAM_TEST_ADMIN_DATABASE_URL:-}" ]]
[[ -n "${WORKSTREAM_TEST_MINIO_ENDPOINT:-}" ]]
echo "qualification stage=host_identity_preflight"
if docker inspect "${CONTAINER}" >/dev/null 2>&1; then
  echo "qualification sibling container already exists" >&2
  exit 1
fi
mkdir -p -- "${SHARED_ROOT}/cache"
chmod 0700 "${SHARED_ROOT}" "${SHARED_ROOT}/cache"
if [[ -e "${SHARED_ROOT}/cache/content" ]]; then
  diff --brief --recursive --no-dereference \
    "${STATE_ROOT}/cache/content" "${SHARED_ROOT}/cache/content" >/dev/null
else
  cp -a -- "${STATE_ROOT}/cache/content" "${SHARED_ROOT}/cache/content"
fi
if [[ -e "${SHARED_ROOT}/cache/cache.sha256" ]]; then
  cmp -- "${STATE_ROOT}/cache/cache.sha256" "${SHARED_ROOT}/cache/cache.sha256"
else
  cp -- "${STATE_ROOT}/cache/cache.sha256" "${SHARED_ROOT}/cache/cache.sha256"
fi
cp -- "${STATE_ROOT}/daemon.json" "${SHARED_ROOT}/daemon.json"
chmod 0444 "${SHARED_ROOT}/cache/cache.sha256"
chmod 0644 "${SHARED_ROOT}/daemon.json"
ORIGINAL_CONFIG_MODE="$(stat -c '%a' "${SHARED_ROOT}/daemon.json")"

readonly PREPARED_IMAGE="$(docker inspect --format '{{.Config.Image}}' "${PREPARED_CONTAINER}")"
[[ "${PREPARED_IMAGE}" =~ @sha256:[a-f0-9]{64}$ ]]
remove_composition_root
(
  cd "${REPOSITORY_ROOT}/backend"
  PYTHONPATH=.:tests .venv/bin/pytest -c pyproject.toml --collect-only -q \
    -p conftest -p tests.checkers.external.conftest \
    ../external_checkers/workstream-checker-service/tests/terminal_systems_runsc_composition.py \
    | grep -Fx \
      '::test_production_service_executes_project_trial_under_runsc_with_real_custody'
)
echo "qualification stage=collection_and_workspace_preflight_complete"
docker create \
  --name "${CONTAINER}" \
  --label "org.workstream.pilot00.run=${RUN_ID}" \
  --label "workstream.qualifier=terminal-systems-runsc" \
  --privileged \
  --network none \
  --security-opt label=disable \
  --mount "type=bind,src=${STATE_ROOT}/dind-state,dst=/var/lib/docker" \
  --mount "type=bind,src=${STATE_ROOT}/tools,dst=/opt/gvisor,readonly" \
  --mount "type=bind,src=${SOCKET_ROOT},dst=${INNER_SOCKET_ROOT}" \
  --mount "type=bind,src=${SHARED_ROOT},dst=${INNER_ROOT}" \
  --mount "type=bind,src=${SHARED_ROOT}/daemon.json,dst=/etc/docker/pilot-daemon.json,readonly" \
  --mount "type=bind,src=${REPOSITORY_ROOT}/experiments/pilot00_gvisor_offline,dst=/pilot,readonly" \
  "${PREPARED_IMAGE}" --config-file=/etc/docker/pilot-daemon.json >/dev/null
QUALIFIER_CONTAINER_OWNED=1

python3 - "${STATE_ROOT}/prepared-assets.json" "${STATE_ROOT}" "${SHARED_ROOT}" "${RUN_ID}" "${CONTAINER}" "${PREPARED_CONTAINER}" <<'PY'
import hashlib
import json
from pathlib import Path
import subprocess
import sys

manifest_path, state_root, shared_root, run_id, container, prepared_container = sys.argv[1:]
manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
expected = {
    "run_id": run_id,
    "container": prepared_container,
    "shared_state_path": state_root,
    "runtime_configuration_path": f"{state_root}/daemon.json",
}
for key, value in expected.items():
    if manifest.get(key) != value:
        raise SystemExit(f"prepared qualification identity differs: {key}")
prepared = json.loads(
    subprocess.check_output(["docker", "inspect", prepared_container], text=True)
)[0]
inspection = json.loads(subprocess.check_output(["docker", "inspect", container], text=True))[0]
if prepared["State"]["Running"]:
    raise SystemExit("prepared qualification container must remain stopped")
if prepared["Config"]["Labels"].get("org.workstream.pilot00.run") != run_id:
    raise SystemExit("prepared qualification container has the wrong owner label")
if inspection["Config"]["Labels"].get("org.workstream.pilot00.run") != run_id:
    raise SystemExit("qualification container has the wrong owner label")
if inspection["Config"]["Labels"].get("workstream.qualifier") != "terminal-systems-runsc":
    raise SystemExit("qualification container has the wrong qualifier label")
if inspection["State"]["Running"]:
    raise SystemExit("qualification requires the owned DIND container to be stopped")
if inspection["Image"] != prepared["Image"]:
    raise SystemExit("qualification container image differs from prepared harness")
mounts = {item["Destination"]: item["Source"] for item in inspection["Mounts"]}
required_mounts = {
    "/workstream-state": shared_root,
    "/var/lib/docker": manifest["docker_state_path"],
    "/opt/gvisor": f"{state_root}/tools",
    "/etc/docker/pilot-daemon.json": f"{shared_root}/daemon.json",
}
if any(mounts.get(destination) != source for destination, source in required_mounts.items()):
    raise SystemExit("qualification container has the wrong shared-state mount")
cache_manifest = Path(shared_root, "cache", "cache.sha256").read_bytes()
if "sha256:" + hashlib.sha256(cache_manifest).hexdigest() != manifest["cache_manifest_sha256"]:
    raise SystemExit("qualification shared cache manifest differs")
PY

docker start "${CONTAINER}" >/dev/null
STARTED=1
for _attempt in $(seq 1 45); do
  if timeout --signal=TERM --kill-after=2s 5s \
    docker exec "${CONTAINER}" docker info >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
timeout --signal=TERM --kill-after=2s 10s \
  docker exec "${CONTAINER}" docker info >/dev/null
readonly HOST_CACHE_MANIFEST_SHA="$(sha256sum "${SHARED_ROOT}/cache/cache.sha256" | awk '{print $1}')"
readonly INNER_CACHE_MANIFEST_SHA="$(docker exec "${CONTAINER}" sha256sum "${INNER_ROOT}/cache/cache.sha256" | awk '{print $1}')"
[[ "${HOST_CACHE_MANIFEST_SHA}" == "${INNER_CACHE_MANIFEST_SHA}" ]]
timeout --signal=TERM --kill-after=2s 10s \
  docker exec "${CONTAINER}" docker info --format '{{json .Runtimes}}' \
  | python3 -c 'import json,sys; assert "runsc" in json.load(sys.stdin)'
echo "qualification stage=sealed_cache_and_runtime_sentinel_complete"
docker stop --time 15 "${CONTAINER}" >/dev/null
STARTED=0

cp -- "${SHARED_ROOT}/daemon.json" "${ORIGINAL_CONFIG}"
python3 - "${STATE_ROOT}/prepared-assets.json" "${ORIGINAL_CONFIG}" "${SHARED_ROOT}/daemon.json" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
source = Path(sys.argv[2]).read_bytes()
actual = "sha256:" + hashlib.sha256(source).hexdigest()
if actual != manifest["runtime_configuration_sha256"]:
    raise SystemExit("prepared daemon configuration digest differs")
value = json.loads(source)
if set(value.get("runtimes", {})) != {"runsc"}:
    raise SystemExit("prepared daemon configuration runtime set differs")
child = value["runtimes"]["runsc"]
arguments = child.get("runtimeArgs")
if not isinstance(arguments, list) or arguments.count("--host-uds=none") != 1:
    raise SystemExit("prepared child runtime host UDS policy differs")
outer = json.loads(json.dumps(child))
outer["runtimeArgs"] = ["--host-uds=open" if item == "--host-uds=none" else item for item in arguments]
value["runtimes"] = {"runsc": outer, "runsc-trial": child}
encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
temporary = Path(sys.argv[3] + ".ws493-new")
temporary.write_bytes(encoded)
temporary.chmod(0o644)
temporary.replace(sys.argv[3])
print("sha256:" + hashlib.sha256(encoded).hexdigest())
PY
CONFIG_REPLACED=1
readonly DUAL_RUNTIME_DIGEST="$(sha256sum "${SHARED_ROOT}/daemon.json" | awk '{print "sha256:" $1}')"

mkdir -p -- "${COMPOSITION_ROOT}/bin" "${COMPOSITION_ROOT}/input" "${COMPOSITION_ROOT}/registry-data"
chmod 0700 "${COMPOSITION_ROOT}" "${COMPOSITION_ROOT}/bin" "${COMPOSITION_ROOT}/input" "${COMPOSITION_ROOT}/registry-data"

(
  cd "${REPOSITORY_ROOT}/external_checkers"
  CARGO_NET_OFFLINE=true CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 RUST_MIN_STACK=67108864 cargo build \
    --locked -p workstream-checker-service --bin workstream-checker-service \
    --message-format=json-render-diagnostics >"${BUILD_MESSAGES}"
)
readonly SERVICE_BINARY="$(python3 - "${BUILD_MESSAGES}" <<'PY'
import json
import sys

values = []
for line in open(sys.argv[1], encoding="utf-8"):
    item = json.loads(line)
    if (
        item.get("reason") == "compiler-artifact"
        and item["target"]["name"] == "workstream-checker-service"
        and "bin" in item["target"]["kind"]
        and item.get("executable")
    ):
        values.append(item["executable"])
if len(values) != 1:
    raise SystemExit("cargo did not report exactly one service executable")
print(values[0])
PY
)"
[[ -x "${SERVICE_BINARY}" ]]
(
  cd "${REPOSITORY_ROOT}"
  CARGO_NET_OFFLINE=true CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo rustc \
    --manifest-path external_checkers/workstream-checker-service/Cargo.toml \
    --bin workstream-trial-launcher --message-format=json-render-diagnostics \
    -- -C target-feature=+crt-static >"${LAUNCHER_MESSAGES}"
)
readonly LAUNCHER_BINARY="$(python3 - "${LAUNCHER_MESSAGES}" <<'PY'
import json
import sys

values = []
for line in open(sys.argv[1], encoding="utf-8"):
    item = json.loads(line)
    if (
        item.get("reason") == "compiler-artifact"
        and item["target"]["name"] == "workstream-trial-launcher"
        and "bin" in item["target"]["kind"]
        and item.get("executable")
    ):
        values.append(item["executable"])
if len(values) != 1:
    raise SystemExit("cargo did not report exactly one launcher executable")
print(values[0])
PY
)"
[[ -x "${LAUNCHER_BINARY}" ]]
readelf -l "${LAUNCHER_BINARY}" >"${LAUNCHER_PROGRAM_HEADERS}"
readelf -d "${LAUNCHER_BINARY}" >"${LAUNCHER_DYNAMIC}"
! grep -q INTERP "${LAUNCHER_PROGRAM_HEADERS}"
! grep -q NEEDED "${LAUNCHER_DYNAMIC}"
cp -- "${SERVICE_BINARY}" "${COMPOSITION_ROOT}/bin/workstream-checker-service"
cp -- "${LAUNCHER_BINARY}" "${COMPOSITION_ROOT}/bin/workstream-trial-launcher"
cp -- "$(readlink -f /lib64/ld-linux-x86-64.so.2)" "${COMPOSITION_ROOT}/bin/ld-linux-x86-64.so.2"
cp -- "$(readlink -f /lib/x86_64-linux-gnu/libgcc_s.so.1)" "${COMPOSITION_ROOT}/bin/libgcc_s.so.1"
cp -- "$(readlink -f /lib/x86_64-linux-gnu/libm.so.6)" "${COMPOSITION_ROOT}/bin/libm.so.6"
cp -- "$(readlink -f /lib/x86_64-linux-gnu/libc.so.6)" "${COMPOSITION_ROOT}/bin/libc.so.6"
chmod 0555 "${COMPOSITION_ROOT}/bin/"*
echo "qualification stage=production_binary_and_project_image_build"

if docker image inspect "${CHECKER_IMAGE}" >/dev/null 2>&1; then
  echo "qualification checker image tag already exists on the host" >&2
  exit 1
fi
docker build --pull=false --network=none --tag "${CHECKER_IMAGE}" \
  --file "${REPOSITORY_ROOT}/pilots/terminal_systems/checkers/post/model/Dockerfile" \
  "${REPOSITORY_ROOT}/pilots/terminal_systems/checkers/post/model" >/dev/null
HOST_CHECKER_BUILT=1
docker image inspect "${CHECKER_IMAGE}" >/dev/null
docker image inspect "${REGISTRY_IMAGE}" >/dev/null
docker save --output "${COMPOSITION_ROOT}/input/checker-image.tar" "${CHECKER_IMAGE}"
docker create --name "${EXTRACT_CONTAINER}" "${REGISTRY_IMAGE}" >/dev/null
EXTRACT_CREATED=1
docker cp "${EXTRACT_CONTAINER}:/bin/registry" "${COMPOSITION_ROOT}/bin/registry"
docker rm "${EXTRACT_CONTAINER}" >/dev/null
EXTRACT_CREATED=0
chmod 0555 "${COMPOSITION_ROOT}/bin/registry"
cat >"${COMPOSITION_ROOT}/registry.yml" <<YAML
version: 0.1
log:
  level: error
storage:
  filesystem:
    rootdirectory: ${INNER_COMPOSITION_ROOT}/registry-data
http:
  addr: 127.0.0.1:5000
YAML
chmod 0444 "${COMPOSITION_ROOT}/registry.yml"

docker start "${CONTAINER}" >/dev/null
STARTED=1
for _attempt in $(seq 1 45); do
  if timeout --signal=TERM --kill-after=2s 5s \
    docker exec "${CONTAINER}" docker info >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
timeout --signal=TERM --kill-after=2s 10s \
  docker exec "${CONTAINER}" docker info >/dev/null
if docker exec "${CONTAINER}" docker image inspect "${CHECKER_IMAGE}" >/dev/null 2>&1; then
  echo "qualification checker image unexpectedly preexists in owned DIND" >&2
  exit 1
fi
test -z "$(docker exec "${CONTAINER}" docker container ls -aq --filter label=workstream.external-checker=true)"
test -z "$(docker exec "${CONTAINER}" docker container ls -aq --filter label=workstream.trial=true)"
test -z "$(docker exec "${CONTAINER}" docker images -q --filter reference='workstream-trial:*')"
docker exec "${CONTAINER}" sh -ceu '
  inner_root="$1"
  composition_root="$2"
  chgrp 1000 /var/run/docker.sock
  chmod 0660 /var/run/docker.sock
  chown -R 1000:1000 "${composition_root}"
  chmod 0711 "${inner_root}"
  nohup "${composition_root}/bin/registry" serve \
    "${composition_root}/registry.yml" \
    >"${composition_root}/registry.log" 2>&1 &
  echo $! >"${composition_root}/registry.pid"
' sh "${INNER_ROOT}" "${INNER_COMPOSITION_ROOT}"
for _attempt in $(seq 1 30); do
  if docker exec "${CONTAINER}" sh -ceu 'wget -q -O /dev/null http://127.0.0.1:5000/v2/'; then
    break
  fi
  sleep 0.2
done
docker exec "${CONTAINER}" sh -ceu 'wget -q -O /dev/null http://127.0.0.1:5000/v2/'
python3 - "${CONTAINER}" <<'PY'
import json
import subprocess
import sys

value = json.loads(
    subprocess.check_output(
        ["docker", "exec", sys.argv[1], "cat", "/etc/docker/pilot-daemon.json"]
    )
)
runtimes = value.get("runtimes", {})
if set(runtimes) != {"runsc", "runsc-trial"}:
    raise SystemExit("qualification runtime keys differ")
outer = runtimes["runsc"].get("runtimeArgs", [])
child = runtimes["runsc-trial"].get("runtimeArgs", [])
if "--host-uds=open" not in outer or any(
    item.startswith("--host-uds=") and item != "--host-uds=open" for item in outer
):
    raise SystemExit("outer host UDS policy differs")
if "--host-uds=none" not in child or any(
    item.startswith("--host-uds=") and item != "--host-uds=none" for item in child
):
    raise SystemExit("child host UDS policy differs")
PY
readonly HOST_SERVICE_SHA="$(sha256sum "${COMPOSITION_ROOT}/bin/workstream-checker-service" | awk '{print $1}')"
readonly INNER_SERVICE_SHA="$(docker exec "${CONTAINER}" sha256sum "${INNER_COMPOSITION_ROOT}/bin/workstream-checker-service" | awk '{print $1}')"
readonly HOST_IMAGE_ARCHIVE_SHA="$(sha256sum "${COMPOSITION_ROOT}/input/checker-image.tar" | awk '{print $1}')"
readonly INNER_IMAGE_ARCHIVE_SHA="$(docker exec "${CONTAINER}" sha256sum "${INNER_COMPOSITION_ROOT}/input/checker-image.tar" | awk '{print $1}')"
[[ "${HOST_SERVICE_SHA}" == "${INNER_SERVICE_SHA}" ]]
[[ "${HOST_IMAGE_ARCHIVE_SHA}" == "${INNER_IMAGE_ARCHIVE_SHA}" ]]
docker exec "${CONTAINER}" test -S /var/run/docker.sock
docker exec --user "$(id -u):$(id -g)" "${CONTAINER}" sh -ceu '
  root="$1"
  test -x "${root}/bin/workstream-checker-service"
  test -x "${root}/bin/registry"
  test -r /workstream-state/cache/cache.sha256
  test -w "${root}"
  "${root}/bin/ld-linux-x86-64.so.2" --library-path "${root}/bin" \
    --list "${root}/bin/workstream-checker-service" >/dev/null
  docker version >/dev/null
' sh "${INNER_COMPOSITION_ROOT}"
echo "qualification stage=inner_paths_uid_and_runtime_preflight_complete"
docker exec "${CONTAINER}" docker load --input "${INNER_COMPOSITION_ROOT}/input/checker-image.tar" >/dev/null
docker exec "${CONTAINER}" docker tag "${CHECKER_IMAGE}" \
  127.0.0.1:5000/terminal-systems-post:qualification
docker exec "${CONTAINER}" docker push \
  127.0.0.1:5000/terminal-systems-post:qualification >/dev/null

readonly CHECKER_INSPECTION="$(docker exec "${CONTAINER}" docker image inspect 127.0.0.1:5000/terminal-systems-post:qualification)"
readonly CHECKER_DIGEST="$(python3 -c 'import json,sys; v=json.load(sys.stdin)[0]; print(next(x.split("@",1)[1] for x in v["RepoDigests"] if x.startswith("127.0.0.1:5000/terminal-systems-post@")))' <<<"${CHECKER_INSPECTION}")"
readonly CHECKER_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["Id"])' <<<"${CHECKER_INSPECTION}")"
readonly PLATFORM_IDENTITY="$(timeout --signal=TERM --kill-after=2s 15s \
  docker exec "${CONTAINER}" docker info --format '{{json .}}' | python3 -c '
import hashlib,json,sys
v=json.load(sys.stdin); key="runsc-trial"; runtime=v["Runtimes"][key]
facts={"architecture":v.get("Architecture"),"cgroup_driver":v.get("CgroupDriver"),"cgroup_version":v.get("CgroupVersion"),"driver":v.get("Driver"),"kernel_version":v.get("KernelVersion"),"operating_system":v.get("OperatingSystem"),"os_type":v.get("OSType"),"runtime":{"path":runtime.get("path"),"runtime_args":runtime.get("runtimeArgs")}}
b=json.dumps(facts,sort_keys=True,separators=(",", ":")).encode(); print("sha256:"+hashlib.sha256(b).hexdigest())
')"

export WORKSTREAM_TS_RUNSC_INNER_ROOT="${INNER_ROOT}"
export WORKSTREAM_TS_RUNSC_SOCKET_ROOT="${SOCKET_ROOT}"
export WORKSTREAM_TS_RUNSC_INNER_SOCKET_ROOT="${INNER_SOCKET_ROOT}"
export WORKSTREAM_TS_RUNSC_COMPOSITION_ROOT="${COMPOSITION_ROOT}"
export WORKSTREAM_TS_RUNSC_INNER_COMPOSITION_ROOT="${INNER_COMPOSITION_ROOT}"
export WORKSTREAM_TS_RUNSC_CONTAINER="${CONTAINER}"
export WORKSTREAM_TS_RUNSC_DAEMON_DIGEST="${DUAL_RUNTIME_DIGEST}"
export WORKSTREAM_TS_RUNSC_PLATFORM_IDENTITY="${PLATFORM_IDENTITY}"
export WORKSTREAM_TS_RUNSC_CHECKER_REPOSITORY="127.0.0.1:5000/terminal-systems-post"
export WORKSTREAM_TS_RUNSC_CHECKER_DIGEST="${CHECKER_DIGEST}"
export WORKSTREAM_TS_RUNSC_CHECKER_ID="${CHECKER_ID}"
export WORKSTREAM_TS_RUNSC_BUILDER_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["builder_image_id"])' "${STATE_ROOT}/prepared-assets.json")"
export WORKSTREAM_TS_RUNSC_BUILDER_MANIFEST="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["builder_manifest"])' "${STATE_ROOT}/prepared-assets.json")"
export WORKSTREAM_TS_RUNSC_CACHE_DIGEST="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["cache_manifest_sha256"])' "${STATE_ROOT}/prepared-assets.json")"
export WORKSTREAM_TS_RUNSC_ENGINE_DIGEST="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["runsc_binary_sha256"])' "${STATE_ROOT}/prepared-assets.json")"
export WORKSTREAM_TS_RUNSC_LAUNCHER_PATH="${INNER_COMPOSITION_ROOT}/bin/workstream-trial-launcher"
export WORKSTREAM_TS_RUNSC_LAUNCHER_DIGEST="sha256:$(sha256sum "${COMPOSITION_ROOT}/bin/workstream-trial-launcher" | cut -d' ' -f1)"

if [[ "${WORKSTREAM_TS_RUNSC_PREFLIGHT_ONLY:-0}" == 1 ]]; then
  echo "qualification stage=preflight_only_complete"
  exit 0
fi
cd "${REPOSITORY_ROOT}/backend"
echo "qualification stage=postgresql_minio_runsc_composition"
set +e
.venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "${METADATA}" --timeout-seconds 900 --lane trial_composition -- \
  env PYTHONPATH=.:tests .venv/bin/pytest -c pyproject.toml -vv -x \
  -p conftest -p tests.checkers.external.conftest -o faulthandler_timeout=120 \
  ../external_checkers/workstream-checker-service/tests/terminal_systems_runsc_composition.py \
  >"${RESULT_LOG}" 2>&1
readonly TEST_STATUS=$?
set -e
cat "${RESULT_LOG}"
exit "${TEST_STATUS}"
