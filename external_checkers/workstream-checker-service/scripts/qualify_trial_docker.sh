#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
readonly STATE_ROOT="${WORKSTREAM_TRIAL_QUALIFICATION_STATE_ROOT:?set the prepared PILOT-00 state root}"
readonly INNER_STATE_ROOT="/workstream-state"
readonly CONTAINER="${WORKSTREAM_TRIAL_QUALIFICATION_CONTAINER:?set the owned qualification container}"
readonly RUN_ID="${WORKSTREAM_TRIAL_QUALIFICATION_RUN_ID:?set the prepared PILOT-00 run ID}"
readonly PLATFORM_IDENTITY="${WORKSTREAM_TRIAL_PLATFORM_IDENTITY_SHA256:?set the exact trusted Docker/runsc platform identity digest}"
readonly RESULT_LOG="$(mktemp /tmp/workstream-trial-qualification.XXXXXX.log)"
readonly BUILD_MESSAGES="$(mktemp /tmp/workstream-trial-build.XXXXXX.jsonl)"
readonly LAUNCHER_MESSAGES="$(mktemp /tmp/workstream-trial-launcher-build.XXXXXX.jsonl)"
readonly LAUNCHER_PROGRAM_HEADERS="$(mktemp /tmp/workstream-trial-launcher.XXXXXX.phdr)"
readonly LAUNCHER_DYNAMIC="$(mktemp /tmp/workstream-trial-launcher.XXXXXX.dynamic)"
trap 'rm -f "${RESULT_LOG}" "${BUILD_MESSAGES}" "${LAUNCHER_MESSAGES}" "${LAUNCHER_PROGRAM_HEADERS}" "${LAUNCHER_DYNAMIC}"' EXIT

[[ "${STATE_ROOT}" == /* ]]
[[ "${RUN_ID}" =~ ^[a-z0-9][a-z0-9-]{0,30}$ ]]
[[ "${PLATFORM_IDENTITY}" =~ ^sha256:[0-9a-f]{64}$ ]]
python3 - "${CONTAINER}" "${RUN_ID}" "${STATE_ROOT}" "${INNER_STATE_ROOT}" <<'PY'
import json
import subprocess
import sys

value = json.loads(subprocess.check_output(["docker", "inspect", sys.argv[1]], text=True))[0]
if value["Config"]["Labels"].get("org.workstream.pilot00.run") != sys.argv[2]:
    raise SystemExit("qualification container has the wrong run label")
if not value["State"]["Running"]:
    raise SystemExit("qualification container is not running")
sources = [mount["Source"] for mount in value["Mounts"] if mount["Destination"] == sys.argv[4]]
if sources != [sys.argv[3]]:
    raise SystemExit("qualification container has the wrong state mount")
PY
docker exec "${CONTAINER}" chmod 0711 "${INNER_STATE_ROOT}"

python3 - "${STATE_ROOT}/prepared-assets.json" "${RUN_ID}" "${STATE_ROOT}" \
  "${REPOSITORY_ROOT}/experiments/pilot00_gvisor_offline/tool-inputs.env" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    value = json.load(stream)
declared = {}
with open(sys.argv[4], encoding="utf-8") as stream:
    for line in stream:
        key, separator, item = line.strip().partition("=")
        if separator:
            declared[key] = item
expected = {
    "run_id": sys.argv[2],
    "shared_state_path": sys.argv[3],
    "docker_state_path": f"{sys.argv[3]}/dind-state",
    "scratch_path": f"{sys.argv[3]}/trial-scratch",
    "cache_path": f"{sys.argv[3]}/cache/content",
    "cache_manifest_path": f"{sys.argv[3]}/cache/cache.sha256",
    "runtime_configuration_path": f"{sys.argv[3]}/daemon.json",
    "protected_role_path": f"{sys.argv[3]}/protected-role",
    "cache_manifest_sha256": "sha256:0d7c48edceae685051d2f60497b0df7f55a0f3f8dd6d29c5e82b9c0cd75a40e1",
    "runtime_configuration_sha256": "sha256:46429fe1ec5b135d7214c1090c28c75a3175169307ae2981c502015152c3d330",
    "runsc_binary_sha256": "sha256:88a87d5d6d06160d4c144f51f95ec6dd6fe0fc6b02697eb877876683c5b57a91",
    "runsc_version": f"runsc version {declared['GVISOR_VERSION']}\nspec: 1.2.1",
    "builder_image_id": declared["KANIKO_IMAGE_ID"],
    "builder_manifest": declared["KANIKO_IMAGE"],
    "base_manifest": declared["BASE_PLATFORM_IMAGE"],
}
for key, expected_value in expected.items():
    if value.get(key) != expected_value:
        raise SystemExit(f"prepared qualification identity differs: {key}")
PY

docker exec "${CONTAINER}" sh -ceu '
  test "$(sha256sum /opt/gvisor/runsc | cut -d" " -f1)" = 88a87d5d6d06160d4c144f51f95ec6dd6fe0fc6b02697eb877876683c5b57a91
  test "$(sha256sum /etc/docker/pilot-daemon.json | cut -d" " -f1)" = 46429fe1ec5b135d7214c1090c28c75a3175169307ae2981c502015152c3d330
  test "$(docker image inspect --format "{{.Id}}" sha256:b8c743a43e82f0cef9956ea09eae79c2d56b51d359b65a736c171624a9fc95e3)" = sha256:b8c743a43e82f0cef9956ea09eae79c2d56b51d359b65a736c171624a9fc95e3
'

(
  cd "${REPOSITORY_ROOT}"
  CARGO_NET_OFFLINE=true CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 RUST_MIN_STACK=67108864 cargo build \
    --manifest-path external_checkers/workstream-checker-service/Cargo.toml \
    --bin qualify-trial-docker --features trial-docker-qualification \
    --message-format=json-render-diagnostics >"${BUILD_MESSAGES}"
)
readonly QUALIFICATION_BINARY="$(python3 - "${BUILD_MESSAGES}" <<'PY'
import json
import sys

executables = []
with open(sys.argv[1], encoding="utf-8") as stream:
    for line in stream:
        value = json.loads(line)
        if (
            value.get("reason") == "compiler-artifact"
            and value["target"]["name"] == "qualify-trial-docker"
            and "bin" in value["target"]["kind"]
            and value.get("executable")
        ):
            executables.append(value["executable"])
if len(executables) != 1:
    raise SystemExit("cargo did not report exactly one qualification executable")
print(executables[0])
PY
)"
[[ -x "${QUALIFICATION_BINARY}" ]]

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

executables = []
with open(sys.argv[1], encoding="utf-8") as stream:
    for line in stream:
        value = json.loads(line)
        if (
            value.get("reason") == "compiler-artifact"
            and value["target"]["name"] == "workstream-trial-launcher"
            and "bin" in value["target"]["kind"]
            and value.get("executable")
        ):
            executables.append(value["executable"])
if len(executables) != 1:
    raise SystemExit("cargo did not report exactly one launcher executable")
print(executables[0])
PY
)"
[[ -x "${LAUNCHER_BINARY}" ]]
readelf -l "${LAUNCHER_BINARY}" >"${LAUNCHER_PROGRAM_HEADERS}"
readelf -d "${LAUNCHER_BINARY}" >"${LAUNCHER_DYNAMIC}"
! grep -q INTERP "${LAUNCHER_PROGRAM_HEADERS}"
! grep -q NEEDED "${LAUNCHER_DYNAMIC}"
readonly LAUNCHER_SHA256="sha256:$(sha256sum "${LAUNCHER_BINARY}" | cut -d' ' -f1)"

docker exec -e QUALIFICATION_ROOT="${INNER_STATE_ROOT}" "${CONTAINER}" sh -ceu '
  chmod 0711 "${QUALIFICATION_ROOT}"
  chown 65532:65532 "${QUALIFICATION_ROOT}/trial-scratch"
  chmod 0700 "${QUALIFICATION_ROOT}/trial-scratch"
  mkdir -p "${QUALIFICATION_ROOT}/qualification-bin" "${QUALIFICATION_ROOT}/results"
  chown 65532:65532 "${QUALIFICATION_ROOT}/results"
  chmod 0755 "${QUALIFICATION_ROOT}/qualification-bin" "${QUALIFICATION_ROOT}/results"
  chgrp 65532 /var/run/docker.sock
  chmod 0660 /var/run/docker.sock
'
docker cp "${QUALIFICATION_BINARY}" "${CONTAINER}:${INNER_STATE_ROOT}/qualification-bin/qualify-trial-docker"
docker cp "${LAUNCHER_BINARY}" "${CONTAINER}:${INNER_STATE_ROOT}/qualification-bin/workstream-trial-launcher"
docker cp "$(readlink -f /lib64/ld-linux-x86-64.so.2)" "${CONTAINER}:${INNER_STATE_ROOT}/qualification-bin/ld-linux-x86-64.so.2"
docker cp "$(readlink -f /lib/x86_64-linux-gnu/libgcc_s.so.1)" "${CONTAINER}:${INNER_STATE_ROOT}/qualification-bin/libgcc_s.so.1"
docker cp "$(readlink -f /lib/x86_64-linux-gnu/libm.so.6)" "${CONTAINER}:${INNER_STATE_ROOT}/qualification-bin/libm.so.6"
docker cp "$(readlink -f /lib/x86_64-linux-gnu/libc.so.6)" "${CONTAINER}:${INNER_STATE_ROOT}/qualification-bin/libc.so.6"
docker exec "${CONTAINER}" chmod 0555 \
  "${INNER_STATE_ROOT}/qualification-bin/qualify-trial-docker" \
  "${INNER_STATE_ROOT}/qualification-bin/workstream-trial-launcher" \
  "${INNER_STATE_ROOT}/qualification-bin/ld-linux-x86-64.so.2" \
  "${INNER_STATE_ROOT}/qualification-bin/libgcc_s.so.1" \
  "${INNER_STATE_ROOT}/qualification-bin/libm.so.6" \
  "${INNER_STATE_ROOT}/qualification-bin/libc.so.6"

docker exec --user 65532:65532 \
  -e WORKSTREAM_TRIAL_QUALIFICATION_ROOT="${INNER_STATE_ROOT}" \
  -e WORKSTREAM_TRIAL_PLATFORM_IDENTITY_SHA256="${PLATFORM_IDENTITY}" \
  -e WORKSTREAM_TRIAL_LAUNCHER_PATH="${INNER_STATE_ROOT}/qualification-bin/workstream-trial-launcher" \
  -e WORKSTREAM_TRIAL_LAUNCHER_SHA256="${LAUNCHER_SHA256}" \
  "${CONTAINER}" \
  "${INNER_STATE_ROOT}/qualification-bin/ld-linux-x86-64.so.2" \
  --library-path "${INNER_STATE_ROOT}/qualification-bin" \
  "${INNER_STATE_ROOT}/qualification-bin/qualify-trial-docker" \
  2>&1 | tee "${RESULT_LOG}"

docker cp "${RESULT_LOG}" "${CONTAINER}:${INNER_STATE_ROOT}/results/trial-docker-qualification.log"
docker exec -e QUALIFICATION_ROOT="${INNER_STATE_ROOT}" "${CONTAINER}" sh -ceu '
  cd "${QUALIFICATION_ROOT}/cache/content"
  sha256sum -c ../cache.sha256 >"${QUALIFICATION_ROOT}/results/trial-cache-recheck.log"
  test -z "$(docker ps -aq --filter label=workstream.trial=true)"
  test -z "$(docker images -q workstream-trial:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)"
  test -z "$(find "${QUALIFICATION_ROOT}/trial-scratch/engine-qualification/runtime" -name ".trial-owner-*.json" -print -quit)"
  test -s "${QUALIFICATION_ROOT}/results/trial-docker-qualification.json"
'
