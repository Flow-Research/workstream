#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=inputs.env
source "${SCRIPT_DIR}/inputs.env"

readonly ACTION="${1:-}"
readonly EXPECTED_HEAD="${WS493_EXPECTED_HEAD:?}"
readonly RUN_ID="${WS493_RUN_ID:?}"
readonly RUNNER_TEMP_ROOT="${RUNNER_TEMP:?}"
[[ "${EXPECTED_HEAD}" =~ ^[0-9a-f]{40}$ ]] || { echo "invalid proof head" >&2; exit 64; }
[[ "${RUN_ID}" =~ ^[0-9]+-[0-9]+$ ]] || { echo "invalid proof run ID" >&2; exit 64; }
[[ "${RUNNER_TEMP_ROOT}" == /* ]] || { echo "RUNNER_TEMP must be absolute" >&2; exit 64; }

readonly OWNER_UID=65532
readonly DOCKER_GID="$(stat -c %g /var/run/docker.sock)"
readonly PROOF_PREFIX="ws493-${RUN_ID}"
readonly PILOT_RUN_ID="pc-${RUN_ID}"
readonly DIND_NAME="ws-pilot00-${PILOT_RUN_ID}-dind"
readonly OUTER_OWNER_LABEL="org.workstream.pilot00.run=${PILOT_RUN_ID}"
readonly RAW_DEVICE_FILE="${RUNNER_TEMP_ROOT}/${PROOF_PREFIX}.xfs"
readonly LOOP_RECORD="${RUNNER_TEMP_ROOT}/${PROOF_PREFIX}.loop"
readonly MOUNT_ROOT="/run/${PROOF_PREFIX}-mount"
readonly STATE_ROOT="${MOUNT_ROOT}/state"
readonly DIND_STATE="${STATE_ROOT}/dind"
readonly CACHE_ROOT="${STATE_ROOT}/cache/content"
readonly RAW_DIR="${STATE_ROOT}/evidence/raw"
readonly ART_ROOT="${STATE_ROOT}/art"
readonly CONTROL_ROOT="/run/${PROOF_PREFIX}-control"
readonly CONTROL_OWNER="${CONTROL_ROOT}/.owner.json"
readonly SERVICE_ROOT="${CONTROL_ROOT}/service"
readonly SOCKET_PATH="${SERVICE_ROOT}/checker.sock"
readonly WRAPPER_WORK="${CONTROL_ROOT}/wrapper"
readonly SERVICE_BUILD_OUTPUT="${REPOSITORY_ROOT}/external_checkers/target/release/workstream-checker-service"
readonly SERVICE_BINARY="${CONTROL_ROOT}/workstream-checker-service"
readonly SERVICE_CONFIG="${SERVICE_ROOT}/config.json"
readonly SERVICE_PID_FILE="${WRAPPER_WORK}/service.pid"
readonly BARRIER_ENABLE="${WRAPPER_WORK}/barrier.enable"
readonly BARRIER_READY="${WRAPPER_WORK}/barrier.ready.json"
readonly BARRIER_RELEASE="${WRAPPER_WORK}/barrier.release"
readonly BARRIER_TOKEN="${EXPECTED_HEAD}-${RUN_ID}"
readonly STAGING_DIR="${RUNNER_TEMP_ROOT}/${PROOF_PREFIX}-staging"
readonly CLEANUP_RECEIPT="${RUNNER_TEMP_ROOT}/${PROOF_PREFIX}-cleanup-receipt.json"
readonly BACKEND_BOOTSTRAP_UV="${REPOSITORY_ROOT}/backend/.venv/bin/uv"
readonly BACKEND_RUNTIME="${CONTROL_ROOT}/python"
readonly BACKEND_PYTHON="${BACKEND_RUNTIME}/bin/python"
readonly PYTHON_SOURCE_ROOT="${CONTROL_ROOT}/python-source"
readonly BACKEND_SOURCE="${PYTHON_SOURCE_ROOT}/backend"
readonly EXECUTE_POST="${PYTHON_SOURCE_ROOT}/scripts/execute_post.py"
readonly MATRIX_BUILDER="${PYTHON_SOURCE_ROOT}/scripts/build_matrix.py"
readonly REAL_DOCKER="$(readlink -f "$(command -v docker)")"
readonly DOCKER_WRAPPER_SOURCE="$(readlink -f "${SCRIPT_DIR}/docker-wrapper.sh")"
readonly DOCKER_WRAPPER="${CONTROL_ROOT}/docker-wrapper.sh"
readonly PILOT_PROBE="${REPOSITORY_ROOT}/experiments/pilot00_gvisor_offline/probe.sh"
readonly PACKAGE="${PYTHON_SOURCE_ROOT}/package"
readonly CRANE_ROOT="${RUNNER_TEMP_ROOT}/ws493-crane"
readonly CRANE_BINARY="${CRANE_ROOT}/crane"
readonly CRANE_ARCHIVE="${RUNNER_TEMP_ROOT}/ws493-crane.tar.gz"

require_command() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing required command: $1" >&2; exit 69; }
}

inner_docker() {
  "${REAL_DOCKER}" exec "${DIND_NAME}" docker "$@"
}

pilot() {
  PILOT00_RUN_ID="${PILOT_RUN_ID}" \
  PILOT00_STATE_DIR="${STATE_ROOT}" \
  PILOT00_DIND_STATE_DIR="${DIND_STATE}" \
  PILOT00_SHARED_STATE_PATH="${STATE_ROOT}" \
  PILOT00_RUNTIME_KEY=runsc \
  PILOT00_HARNESS_ONLY=1 \
    "${PILOT_PROBE}" "$@"
}

write_owned_json() {
  local destination="$1"
  shift
  python3 - "${destination}" "$@" <<'PY'
import json
import os
import sys

destination = sys.argv[1]
value = json.loads(sys.argv[2])
payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
try:
    os.write(descriptor, payload)
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
  chown "${OWNER_UID}:${DOCKER_GID}" "${destination}"
}

create_control_custody() {
  python3 - "${CONTROL_ROOT}" "${CONTROL_OWNER}" "${EXPECTED_HEAD}" "${RUN_ID}" \
    "${SERVICE_BUILD_OUTPUT}" "${SERVICE_BINARY}" \
    "${DOCKER_WRAPPER_SOURCE}" "${DOCKER_WRAPPER}" <<'PY'
import ctypes
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile

(root, owner_path, head_sha, run_id, service_source, service_path,
 wrapper_source, wrapper_path) = sys.argv[1:]
parent = os.path.dirname(root)
temporary = tempfile.mkdtemp(prefix=f".{os.path.basename(root)}.", dir=parent)
renamed = False
try:
    os.chmod(temporary, 0o755)
    def copy_exact(source_path: str, target_path: str) -> str:
        source_stat = os.lstat(source_path)
        if not stat.S_ISREG(source_stat.st_mode) or not 0 < source_stat.st_size <= 134_217_728:
            raise SystemExit("control executable source metadata differs")
        source = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW)
        copied_path = os.path.join(temporary, os.path.basename(target_path))
        destination = os.open(
            copied_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o555,
        )
        digest = hashlib.sha256()
        try:
            while True:
                chunk = os.read(source, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                view = memoryview(chunk)
                while view:
                    written = os.write(destination, view)
                    if written <= 0:
                        raise OSError("control executable copy made no progress")
                    view = view[written:]
            os.fchmod(destination, 0o555)
            os.fsync(destination)
            opened_source = os.fstat(source)
            if (
                opened_source.st_dev,
                opened_source.st_ino,
                opened_source.st_size,
                opened_source.st_mtime_ns,
            ) != (
                source_stat.st_dev,
                source_stat.st_ino,
                source_stat.st_size,
                source_stat.st_mtime_ns,
            ):
                raise SystemExit("control executable source changed")
        finally:
            os.close(destination)
            os.close(source)
        return digest.hexdigest()

    service_sha256 = copy_exact(service_source, service_path)
    wrapper_sha256 = copy_exact(wrapper_source, wrapper_path)
    marker = os.path.join(temporary, os.path.basename(owner_path))
    payload = (
        json.dumps(
            {
                "head_sha": head_sha,
                "run_id": run_id,
                "schema_version": "workstream.ws493.control-owner.v1",
                "service_sha256": service_sha256,
                "wrapper_sha256": wrapper_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    descriptor = os.open(
        marker,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
        0o600,
    )
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)

    renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(-100, os.fsencode(temporary), -100, os.fsencode(root), 1) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), root)
    renamed = True
finally:
    if not renamed:
        shutil.rmtree(temporary)
PY
}

control_custody_valid() {
  python3 - "${CONTROL_ROOT}" "${CONTROL_OWNER}" "${EXPECTED_HEAD}" "${RUN_ID}" \
    "${SERVICE_BINARY}" "${DOCKER_WRAPPER}" <<'PY'
import hashlib
import json
import os
import stat
import sys

root, owner_path, head_sha, run_id, service_path, wrapper_path = sys.argv[1:]
root_stat = os.lstat(root)
if not stat.S_ISDIR(root_stat.st_mode) or stat.S_IMODE(root_stat.st_mode) != 0o755:
    raise SystemExit("control root type or mode differs")
if (root_stat.st_uid, root_stat.st_gid) != (0, 0):
    raise SystemExit("control root owner differs")
owner_stat = os.lstat(owner_path)
if not stat.S_ISREG(owner_stat.st_mode) or stat.S_IMODE(owner_stat.st_mode) != 0o600:
    raise SystemExit("control owner type or mode differs")
if (owner_stat.st_uid, owner_stat.st_gid) != (0, 0) or owner_stat.st_size > 4096:
    raise SystemExit("control owner metadata differs")
descriptor = os.open(owner_path, os.O_RDONLY | os.O_NOFOLLOW)
try:
    opened = os.fstat(descriptor)
    if (opened.st_dev, opened.st_ino) != (owner_stat.st_dev, owner_stat.st_ino):
        raise SystemExit("control owner changed")
    payload = os.read(descriptor, 4097)
finally:
    os.close(descriptor)
value = json.loads(payload)
service_sha256 = value.get("service_sha256")
wrapper_sha256 = value.get("wrapper_sha256")
if not all(
    isinstance(digest, str) and len(digest) == 64
    for digest in (service_sha256, wrapper_sha256)
):
    raise SystemExit("control executable digest differs")
expected = {
    "head_sha": head_sha,
    "run_id": run_id,
    "schema_version": "workstream.ws493.control-owner.v1",
    "service_sha256": service_sha256,
    "wrapper_sha256": wrapper_sha256,
}
if payload != (json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n").encode():
    raise SystemExit("control owner binding differs")
def verify_exact(path: str, expected_digest: str) -> None:
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o555:
        raise SystemExit("control executable type or mode differs")
    if (metadata.st_uid, metadata.st_gid) != (0, 0) or not 0 < metadata.st_size <= 134_217_728:
        raise SystemExit("control executable metadata differs")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise SystemExit("control executable changed")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(descriptor)
    if digest.hexdigest() != expected_digest:
        raise SystemExit("control executable digest differs")

verify_exact(service_path, service_sha256)
verify_exact(wrapper_path, wrapper_sha256)
PY
}

assert_source_head() {
  local -a git_command=(git -c "safe.directory=${REPOSITORY_ROOT}" -C "${REPOSITORY_ROOT}")
  [[ "$("${git_command[@]}" rev-parse HEAD)" == "${EXPECTED_HEAD}" ]]
  [[ -z "$("${git_command[@]}" status --porcelain=v1)" ]]
}

preflight() {
  local available_disk available_memory cpus
  available_disk="$(df --output=avail -B1 "${RUNNER_TEMP_ROOT}" | tail -1 | tr -d ' ')"
  available_memory="$(awk '/^MemAvailable:/ {print $2 * 1024}' /proc/meminfo)"
  cpus="$(nproc)"
  (( available_disk >= 10 * 1024 * 1024 * 1024 )) || { echo "less than 10 GiB available" >&2; exit 69; }
  (( available_memory >= 6 * 1024 * 1024 * 1024 )) || { echo "less than 6 GiB memory available" >&2; exit 69; }
  (( cpus >= 2 )) || { echo "fewer than 2 CPUs available" >&2; exit 69; }
}

manifest_raw() {
  local reference="$1" output="$2"
  docker buildx imagetools inspect --raw "${reference}" >"${output}"
}

inner_repository_digest() {
  local reference="$1" repository="$2"
  inner_docker image inspect "${reference}" --format '{{json .RepoDigests}}' | \
    python3 -c 'import json,sys; matches=[value for value in json.load(sys.stdin) if value.startswith(sys.argv[1]+"@")]; len(matches) == 1 or sys.exit(1); print(matches[0])' "${repository}"
}

recorded_image_reference() {
  local name="$1"
  python3 -c 'import json,sys; value=json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]]; print(value["repository"]+"@"+value["platform_manifest_digest"])' \
    "${RAW_DIR}/image-facts.json" "${name}"
}

prepare_filesystem() {
  [[ "$(id -u)" -eq 0 ]] || { echo "proof preparation requires root" >&2; exit 77; }
  [[ ! -e "${RAW_DEVICE_FILE}" && ! -e "${LOOP_RECORD}" && ! -e "${MOUNT_ROOT}" ]]
  truncate -s 6G "${RAW_DEVICE_FILE}"
  local loop_device
  loop_device="$(losetup --find --show "${RAW_DEVICE_FILE}")"
  printf '%s\n' "${loop_device}" >"${LOOP_RECORD}"
  chmod 0600 "${LOOP_RECORD}"
  mkfs.xfs -f -n ftype=1 "${loop_device}" >/dev/null
  mkdir -m 0755 "${MOUNT_ROOT}"
  mount -o pquota "${loop_device}" "${MOUNT_ROOT}"
  [[ "$(findmnt -n -o SOURCE --target "${MOUNT_ROOT}")" == "${loop_device}" ]]
  [[ "$(findmnt -n -o FSTYPE --target "${MOUNT_ROOT}")" == xfs ]]
  findmnt -n -o OPTIONS --target "${MOUNT_ROOT}" | grep -Eq '(^|,)(pquota|prjquota)(,|$)'
  xfs_quota -x -c 'state -p' "${MOUNT_ROOT}" | grep -F 'Project quota state' >/dev/null
}

prepare_images() {
  local work="${STATE_ROOT}/work"
  install -d -m 0700 "${work}"
  manifest_raw "${KANIKO_INDEX}" "${work}/kaniko-index.json"
  local kaniko_index_digest="${KANIKO_INDEX##*@}"
  local kaniko_child
  kaniko_child="$(python3 "${SCRIPT_DIR}/image_facts.py" select-child "${work}/kaniko-index.json" "${kaniko_index_digest}")"
  local kaniko_repository="${KANIKO_INDEX%@*}"
  local kaniko_reference="${kaniko_repository}@${kaniko_child}"
  local registry_transfer="ws493-registry:${EXPECTED_HEAD}"
  "${CRANE_BINARY}" pull "${kaniko_reference}" "${work}/builder-oci" --format=oci
  python3 "${SCRIPT_DIR}/image_facts.py" layout-fact \
    "${work}/builder-oci" "${kaniko_child}" "${kaniko_repository}" >"${work}/upstream-builder-fact.json"
  "${CRANE_BINARY}" pull "${BASE_PLATFORM_IMAGE}" "${work}/base-oci" --format=oci
  python3 "${SCRIPT_DIR}/image_facts.py" layout-fact \
    "${work}/base-oci" "${BASE_PLATFORM_IMAGE##*@}" "${BASE_PLATFORM_IMAGE%@*}" >"${work}/upstream-base-fact.json"

  docker pull "${REGISTRY_IMAGE}" >/dev/null
  docker pull "${CHECKER_BUILD_IMAGE}" >/dev/null
  docker pull "${CHECKER_FINAL_IMAGE}" >/dev/null
  docker build --pull=false --tag "ws493-checker:${EXPECTED_HEAD}" \
    --file "${REPOSITORY_ROOT}/external_checkers/workstream-terminal-benchmark-checker/Dockerfile" \
    "${REPOSITORY_ROOT}/external_checkers" >/dev/null
  printf 'ws493_prepare=outer_images_ready\n'

  docker tag "${REGISTRY_IMAGE}" "${registry_transfer}"
  docker save "${registry_transfer}" | "${REAL_DOCKER}" exec -i "${DIND_NAME}" docker load >/dev/null
  docker save "ws493-checker:${EXPECTED_HEAD}" | "${REAL_DOCKER}" exec -i "${DIND_NAME}" docker load >/dev/null
  inner_docker image inspect "${registry_transfer}" >/dev/null
  "${REAL_DOCKER}" cp "${CRANE_BINARY}" "${DIND_NAME}:/usr/local/bin/ws493-crane"
  local crane_sha
  crane_sha="$(sha256sum "${CRANE_BINARY}" | cut -d' ' -f1)"
  [[ "$("${REAL_DOCKER}" exec "${DIND_NAME}" sha256sum /usr/local/bin/ws493-crane | cut -d' ' -f1)" == "${crane_sha}" ]]
  printf 'ws493_prepare=inner_transport_ready\n'

  inner_docker run -d --name "${PROOF_PREFIX}-registry" \
    --label "org.workstream.ws493.run=${RUN_ID}" --network host \
    "${registry_transfer}" >/dev/null
  for _ in $(seq 1 60); do
    if "${REAL_DOCKER}" exec "${DIND_NAME}" wget -qO- http://127.0.0.1:5000/v2/ >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  "${REAL_DOCKER}" exec "${DIND_NAME}" wget -qO- http://127.0.0.1:5000/v2/ >/dev/null
  printf 'ws493_prepare=loopback_registry_ready\n'
  local builder_repository=127.0.0.1:5000/workstream/builder
  local builder_tag="${builder_repository}:${EXPECTED_HEAD}"
  "${REAL_DOCKER}" exec "${DIND_NAME}" /usr/local/bin/ws493-crane push \
    --insecure "${work}/builder-oci" "${builder_tag}" >/dev/null
  local builder_digest="${kaniko_child}"
  local builder_reference="${builder_repository}@${builder_digest}"
  "${REAL_DOCKER}" exec "${DIND_NAME}" wget -qO "${work}/builder-manifest.json" \
    --header 'Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
    "http://127.0.0.1:5000/v2/workstream/builder/manifests/${builder_digest}"
  python3 "${SCRIPT_DIR}/image_facts.py" manifest-fact \
    "${work}/builder-manifest.json" "${builder_digest}" "${builder_repository}" >"${work}/builder-fact.json"
  inner_docker pull "${builder_reference}" >/dev/null
  [[ "$(inner_repository_digest "${builder_reference}" "${builder_repository}")" == "${builder_reference}" ]]
  printf 'ws493_prepare=builder_manifest_verified\n'
  local base_repository=127.0.0.1:5000/workstream/base
  local base_tag="${base_repository}:${EXPECTED_HEAD}"
  "${REAL_DOCKER}" exec "${DIND_NAME}" /usr/local/bin/ws493-crane push \
    --insecure "${work}/base-oci" "${base_tag}" >/dev/null
  local base_digest="${BASE_PLATFORM_IMAGE##*@}"
  local base_reference="${base_repository}@${base_digest}"
  "${REAL_DOCKER}" exec "${DIND_NAME}" wget -qO "${work}/base-manifest.json" \
    --header 'Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
    "http://127.0.0.1:5000/v2/workstream/base/manifests/${base_digest}"
  python3 "${SCRIPT_DIR}/image_facts.py" manifest-fact \
    "${work}/base-manifest.json" "${base_digest}" "${base_repository}" >"${work}/base-fact.json"
  inner_docker pull "${base_reference}" >/dev/null
  [[ "$(inner_repository_digest "${base_reference}" "${base_repository}")" == "${base_reference}" ]]
  printf 'ws493_prepare=base_manifest_verified\n'
  mkdir -p "${CACHE_ROOT}"
  inner_docker run --rm --pull=never --name "${PROOF_PREFIX}-cache-warmer" \
    --label "org.workstream.ws493.run=${RUN_ID}" --network host --user 0:0 \
    --cpus 1 --memory 1g --pids-limit 128 \
    --cap-drop ALL --security-opt no-new-privileges \
    --mount "type=bind,src=${CACHE_ROOT},dst=/cache" \
    --entrypoint /kaniko/warmer "${builder_reference}" \
    --cache-dir=/cache --image="${base_reference}" \
    --insecure-registry=127.0.0.1:5000
  chown -R "${OWNER_UID}:${DOCKER_GID}" "${CACHE_ROOT}"
  find "${CACHE_ROOT}" -type d -exec chmod 0555 {} +
  find "${CACHE_ROOT}" -type f -exec chmod 0444 {} +
  local checker_repository=127.0.0.1:5000/workstream/checker
  local checker_tag="${checker_repository}:${EXPECTED_HEAD}"
  inner_docker tag "ws493-checker:${EXPECTED_HEAD}" "${checker_tag}"
  inner_docker push "${checker_tag}" >/dev/null
  local checker_reference checker_digest
  checker_reference="$(inner_repository_digest "${checker_tag}" "${checker_repository}")"
  checker_digest="${checker_reference##*@}"
  [[ "${checker_reference}" == "${checker_repository}@${checker_digest}" ]]
  "${REAL_DOCKER}" exec "${DIND_NAME}" wget -qO "${work}/checker-manifest.json" \
    --header 'Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
    "http://127.0.0.1:5000/v2/workstream/checker/manifests/${checker_digest}"
  printf 'ws493_prepare=loopback_images_and_cache_ready\n'

  python3 "${SCRIPT_DIR}/image_facts.py" manifest-fact \
    "${work}/checker-manifest.json" "${checker_digest}" "${checker_repository}" >"${work}/checker-fact.json"
  python3 - "${work}" "${RAW_DIR}/image-facts.json" <<'PY'
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
value = {
    "approved_base": json.loads((root / "base-fact.json").read_text()),
    "builder": json.loads((root / "builder-fact.json").read_text()),
    "checker": json.loads((root / "checker-fact.json").read_text()),
}
with open(sys.argv[2], "x", encoding="utf-8") as stream:
    json.dump(value, stream, separators=(",", ":"), sort_keys=True)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
PY
  chown "${OWNER_UID}:${DOCKER_GID}" "${RAW_DIR}/image-facts.json"
  chmod 0600 "${RAW_DIR}/image-facts.json"
}

quota_and_boundaries() {
  local base work="${STATE_ROOT}/work"
  base="$(recorded_image_reference approved_base)"
  local below="${PROOF_PREFIX}-quota-below" above="${PROOF_PREFIX}-quota-above"
  inner_docker create --pull=never --name "${below}" --runtime runsc --network none \
    --storage-opt size=402653184 "${base}" python -c \
    'import os; f=open("/quota.bin","wb",buffering=0); [f.write(b"x"*(1024*1024)) for _ in range(320)]; os.fsync(f.fileno())' >/dev/null
  inner_docker start --attach "${below}" >"${work}/quota-below.log" 2>&1
  [[ "$(inner_docker inspect "${below}" --format '{{.State.ExitCode}}')" == 0 ]]
  inner_docker rm -v "${below}" >/dev/null

  inner_docker create --pull=never --name "${above}" --runtime runsc --network none \
    --storage-opt size=402653184 "${base}" python -c \
    'import os; f=open("/quota.bin","wb",buffering=0); [f.write(b"x"*(1024*1024)) for _ in range(400)]; os.fsync(f.fileno())' >/dev/null
  set +e
  inner_docker start --attach "${above}" >"${work}/quota-above.log" 2>&1
  local above_status=$?
  set -e
  [[ "${above_status}" -ne 0 ]]
  [[ "$(inner_docker inspect "${above}" --format '{{.State.ExitCode}}')" != 0 ]]
  inner_docker rm -v "${above}" >/dev/null

  inner_docker info --format '{{json .}}' >"${work}/docker-info.json"
  xfs_quota -x -c 'state -p' "${MOUNT_ROOT}" >"${work}/xfs-quota.txt"
  python3 - "${work}/docker-info.json" "${work}/xfs-quota.txt" "${RAW_DIR}/quota.json" <<'PY'
import json
import os
import sys

info = json.load(open(sys.argv[1], encoding="utf-8"))
driver = dict(info.get("DriverStatus") or [])
quota = open(sys.argv[2], encoding="utf-8").read().lower()
value = {
    "backing_filesystem": str(driver.get("Backing Filesystem", "")).lower(),
    "d_type": str(driver.get("Supports d_type", "")).lower() == "true",
    "inner_driver": info.get("Driver"),
    "project_quota": "accounting: on" in quota and "enforcement: on" in quota,
    "storage_opt_bytes": 402653184,
    "below_limit_bytes": 335544320,
    "below_limit_succeeded": True,
    "above_limit_bytes": 419430400,
    "above_limit_failed": True,
}

if value != {
    "backing_filesystem": "xfs", "d_type": True, "inner_driver": "overlay2",
    "project_quota": True, "storage_opt_bytes": 402653184,
    "below_limit_bytes": 335544320, "below_limit_succeeded": True,
    "above_limit_bytes": 419430400, "above_limit_failed": True,
}:
    raise SystemExit("quota facts differ")
with open(sys.argv[3], "x", encoding="utf-8") as stream:
    json.dump(value, stream, separators=(",", ":"), sort_keys=True)
    stream.write("\n")
    stream.flush(); os.fsync(stream.fileno())
PY

  local builder
  builder="$(recorded_image_reference builder)"
  inner_docker run --rm --pull=never --runtime runsc --network none --user 0:0 \
    --cap-drop ALL --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER --cap-add SYS_CHROOT \
    --security-opt no-new-privileges --entrypoint /busybox/sh "${builder}" -ceu '
      test -e /proc/gvisor/kernel_is_gvisor
      test ! -e /var/run/docker.sock && test ! -e /run/docker.sock
      test "$(awk "NR > 2 { count += 1 } END { print count + 0 }" /proc/net/dev)" -eq 1
      grep -Eq "^[[:space:]]*lo:" /proc/net/dev
      printf "builder_runtime=gvisor\nbuilder_network=loopback-only\nbuilder_host_socket=absent\n"
    ' >"${RAW_DIR}/builder-boundary.log"
  inner_docker run --rm --pull=never --runtime runsc --network none --read-only \
    --user 65532:65532 --cap-drop ALL --security-opt no-new-privileges \
    "${base}" python -c '
import pathlib
assert pathlib.Path("/proc/gvisor/kernel_is_gvisor").exists()
assert not pathlib.Path("/var/run/docker.sock").exists()
assert not pathlib.Path("/run/docker.sock").exists()
interfaces=[line.split(":",1)[0].strip() for line in pathlib.Path("/proc/net/dev").read_text().splitlines()[2:]]
assert interfaces == ["lo"]
print("oracle_runtime=gvisor\noracle_network=loopback-only\noracle_host_socket=absent")
' >"${RAW_DIR}/base-boundary.log"
  chown "${OWNER_UID}:${DOCKER_GID}" "${RAW_DIR}/quota.json" "${RAW_DIR}/builder-boundary.log" "${RAW_DIR}/base-boundary.log"
  chmod 0600 "${RAW_DIR}/quota.json" "${RAW_DIR}/builder-boundary.log" "${RAW_DIR}/base-boundary.log"
}

capture_harness_boundary() {
  install -d -m 0700 "${STATE_ROOT}/work"
  docker inspect "${DIND_NAME}" >"${STATE_ROOT}/work/dind-inspect.json"
  inner_docker info --format '{{json .Runtimes}}' >"${STATE_ROOT}/work/dind-runtimes.json"
  python3 - "${STATE_ROOT}/work/dind-inspect.json" "${STATE_ROOT}/work/dind-runtimes.json" \
    "${RAW_DIR}/harness.json" "${STATE_ROOT}" "${DIND_STATE}" "${RUN_ID}" <<'PY'
import json
import os
import sys

[item] = json.load(open(sys.argv[1], encoding="utf-8"))
runtimes = json.load(open(sys.argv[2], encoding="utf-8"))
host = item["HostConfig"]
mounts = {mount["Destination"]: mount["Source"] for mount in item["Mounts"]}
if item.get("Config", {}).get("Labels", {}).get("org.workstream.pilot00.run") != f"pc-{sys.argv[6]}":
    raise SystemExit("DIND owner differs")
value = {
    "cpu_nanos": host.get("NanoCpus"),
    "external_network": host.get("NetworkMode"),
    "memory_bytes": host.get("Memory"),
    "pids_limit": host.get("PidsLimit"),
    "privileged": host.get("Privileged"),
    "runtime_key": "runsc" if "runsc" in runtimes else None,
    "same_absolute_state_mount": mounts.get(sys.argv[4]) == sys.argv[4],
    "xfs_docker_state_mount": mounts.get("/var/lib/docker") == sys.argv[5],
}
expected = {
    "cpu_nanos": 2_000_000_000,
    "external_network": "none",
    "memory_bytes": 4_294_967_296,
    "pids_limit": 768,
    "privileged": True,
    "runtime_key": "runsc",
    "same_absolute_state_mount": True,
    "xfs_docker_state_mount": True,
}
if value != expected:
    raise SystemExit("DIND boundary differs")
with open(sys.argv[3], "x", encoding="utf-8") as stream:
    json.dump(value, stream, separators=(",", ":"), sort_keys=True)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
PY
  chown "${OWNER_UID}:${DOCKER_GID}" "${RAW_DIR}/harness.json"
  chmod 0600 "${RAW_DIR}/harness.json"
}

stage_python_sources() {
  python3 - "${REPOSITORY_ROOT}" "${PYTHON_SOURCE_ROOT}" "${EXPECTED_HEAD}" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

repository = Path(sys.argv[1])
destination = Path(sys.argv[2])
expected_head = sys.argv[3]
prefixes = (
    "backend/app",
    "experiments/terminal_benchmark_project_checkers/execute_post.py",
    "experiments/terminal_benchmark_project_checkers/build_matrix.py",
    "pilots/terminal_benchmark/packages/ledger-reconcile",
)
if (
    len(expected_head) != 40
    or any(character not in "0123456789abcdef" for character in expected_head)
    or subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
    ).strip()
    != expected_head
):
    raise SystemExit("proof Python source head differs")
listed = subprocess.check_output(
    [
        "git", "-C", str(repository), "ls-tree", "-rz", "--full-tree",
        expected_head, "--", *prefixes,
    ]
).split(b"\0")
tracked = []
for record in listed:
    if not record:
        continue
    metadata, raw_path = record.split(b"\t", 1)
    mode, kind, raw_object_id = metadata.split(b" ")
    object_id = raw_object_id.decode("ascii")
    if (
        kind != b"blob"
        or mode not in (b"100644", b"100755")
        or len(object_id) not in (40, 64)
        or any(character not in "0123456789abcdef" for character in object_id)
    ):
        raise SystemExit("proof Python HEAD entry differs")
    tracked.append((Path(os.fsdecode(raw_path)), object_id))
tracked.sort(key=lambda item: item[0])
paths = [path for path, _ in tracked]
required = {
    Path("experiments/terminal_benchmark_project_checkers/execute_post.py"),
    Path("experiments/terminal_benchmark_project_checkers/build_matrix.py"),
}
package_prefix = Path("pilots/terminal_benchmark/packages/ledger-reconcile")
if (
    not required.issubset(paths)
    or not any(path.parts[:2] == ("backend", "app") for path in paths)
    or not any(path.is_relative_to(package_prefix) for path in paths)
):
    raise SystemExit("proof Python source inventory differs")
if len(paths) > 4096:
    raise SystemExit("proof Python source entry limit exceeded")
os.mkdir(destination, 0o755)
entries = []
total_bytes = 0

def target_for(relative: Path) -> Path:
    if relative.parts[:2] == ("backend", "app"):
        return destination / "backend" / Path(*relative.parts[1:])
    if relative in required:
        return destination / "scripts" / relative.name
    try:
        remainder = relative.relative_to(package_prefix)
    except ValueError as error:
        raise SystemExit("proof Python source path differs") from error
    return destination / "package" / remainder

for relative, object_id in tracked:
    source = repository / relative
    metadata = os.lstat(source)
    if not stat.S_ISREG(metadata.st_mode):
        raise SystemExit("proof Python source is not regular")
    total_bytes += metadata.st_size
    if total_bytes > 67_108_864:
        raise SystemExit("proof Python source byte limit exceeded")
    target = target_for(relative)
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    source_descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    target_descriptor = os.open(
        target,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
        0o444,
    )
    digest = hashlib.sha256()
    head_digest = hashlib.sha1() if len(object_id) == 40 else hashlib.sha256()
    head_digest.update(f"blob {metadata.st_size}\0".encode())
    count = 0
    try:
        while True:
            chunk = os.read(source_descriptor, 1024 * 1024)
            if not chunk:
                break
            count += len(chunk)
            digest.update(chunk)
            head_digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(target_descriptor, view)
                if written <= 0:
                    raise OSError("proof Python source copy made no progress")
                view = view[written:]
        os.fchmod(target_descriptor, 0o444)
        os.fsync(target_descriptor)
        opened = os.fstat(source_descriptor)
    finally:
        os.close(target_descriptor)
        os.close(source_descriptor)
    if (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
    ) != (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
    ) or count != metadata.st_size:
        raise SystemExit("proof Python source changed")
    expected_digest = digest.hexdigest()
    if head_digest.hexdigest() != object_id:
        raise SystemExit("proof Python source differs from HEAD")
    entries.append(
        {
            "byte_count": count,
            "git_blob_oid": object_id,
            "path": target.relative_to(destination).as_posix(),
            "sha256": expected_digest,
        }
    )

entries.sort(key=lambda entry: entry["path"])
inventory = {
    "entries": entries,
    "head_sha": expected_head,
    "schema_version": "workstream.ws493.python-source.v1",
    "total_bytes": total_bytes,
    "total_count": len(entries),
}
inventory_path = destination / ".inventory.json"
payload = (json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n").encode()
descriptor = os.open(
    inventory_path,
    os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
    0o444,
)
try:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("proof Python inventory write made no progress")
        view = view[written:]
    os.fchmod(descriptor, 0o444)
    os.fsync(descriptor)
finally:
    os.close(descriptor)
for current, directories, _ in os.walk(destination, topdown=False, followlinks=False):
    if any((Path(current) / name).is_symlink() for name in directories):
        raise SystemExit("proof Python source link rejected")
    os.chmod(current, 0o555)
PY
}

python_sources_valid() {
  python3 - "${PYTHON_SOURCE_ROOT}" "${EXPECTED_HEAD}" <<'PY'
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys

root = Path(sys.argv[1])
expected_head = sys.argv[2]
maximum_count = 4096
maximum_bytes = 67_108_864
maximum_inventory_bytes = 16_777_216

root_metadata = os.lstat(root)
if (
    not stat.S_ISDIR(root_metadata.st_mode)
    or stat.S_IMODE(root_metadata.st_mode) != 0o555
    or (root_metadata.st_uid, root_metadata.st_gid) != (0, 0)
):
    raise SystemExit("proof Python source root metadata differs")

inventory_path = root / ".inventory.json"
inventory_metadata = os.lstat(inventory_path)
if (
    not stat.S_ISREG(inventory_metadata.st_mode)
    or stat.S_IMODE(inventory_metadata.st_mode) != 0o444
    or (inventory_metadata.st_uid, inventory_metadata.st_gid) != (0, 0)
    or not 0 < inventory_metadata.st_size <= maximum_inventory_bytes
):
    raise SystemExit("proof Python inventory metadata differs")
descriptor = os.open(inventory_path, os.O_RDONLY | os.O_NOFOLLOW)
try:
    opened = os.fstat(descriptor)
    if (opened.st_dev, opened.st_ino) != (
        inventory_metadata.st_dev,
        inventory_metadata.st_ino,
    ):
        raise SystemExit("proof Python inventory changed")
    payload = os.read(descriptor, maximum_inventory_bytes + 1)
finally:
    os.close(descriptor)
if len(payload) != inventory_metadata.st_size:
    raise SystemExit("proof Python inventory size differs")
value = json.loads(payload)
if set(value) != {
    "entries", "head_sha", "schema_version", "total_bytes", "total_count",
}:
    raise SystemExit("proof Python inventory fields differ")
entries = value.get("entries")
if (
    value.get("schema_version") != "workstream.ws493.python-source.v1"
    or value.get("head_sha") != expected_head
    or not isinstance(entries, list)
    or not isinstance(value.get("total_count"), int)
    or not isinstance(value.get("total_bytes"), int)
    or not 0 < value["total_count"] <= maximum_count
    or not 0 <= value["total_bytes"] <= maximum_bytes
    or value["total_count"] != len(entries)
):
    raise SystemExit("proof Python inventory bounds differ")
if payload != (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode():
    raise SystemExit("proof Python inventory encoding differs")

expected_files = set()
expected_directories = {"."}
validated_bytes = 0
previous_path = None
for entry in entries:
    if set(entry) != {"byte_count", "git_blob_oid", "path", "sha256"}:
        raise SystemExit("proof Python inventory entry fields differ")
    relative_value = entry.get("path")
    byte_count = entry.get("byte_count")
    git_blob_oid = entry.get("git_blob_oid")
    expected_digest = entry.get("sha256")
    if (
        not isinstance(relative_value, str)
        or not isinstance(byte_count, int)
        or byte_count < 0
        or not isinstance(expected_digest, str)
        or len(expected_digest) != 64
        or any(character not in "0123456789abcdef" for character in expected_digest)
        or not isinstance(git_blob_oid, str)
        or len(git_blob_oid) not in (40, 64)
        or any(character not in "0123456789abcdef" for character in git_blob_oid)
    ):
        raise SystemExit("proof Python inventory entry differs")
    relative = PurePosixPath(relative_value)
    if (
        relative.is_absolute()
        or relative.as_posix() != relative_value
        or not relative.parts
        or any(part in ("", ".", "..") for part in relative.parts)
        or relative_value == ".inventory.json"
        or previous_path is not None and relative_value <= previous_path
    ):
        raise SystemExit("proof Python inventory path differs")
    previous_path = relative_value
    expected_files.add(relative_value)
    for parent in relative.parents:
        expected_directories.add(parent.as_posix())

    path = root.joinpath(*relative.parts)
    metadata = os.lstat(path)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o444
        or (metadata.st_uid, metadata.st_gid) != (0, 0)
        or metadata.st_size != byte_count
    ):
        raise SystemExit("proof Python source metadata differs")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    digest = hashlib.sha256()
    count = 0
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise SystemExit("proof Python source changed")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            count += len(chunk)
            digest.update(chunk)
    finally:
        os.close(descriptor)
    if count != byte_count or digest.hexdigest() != expected_digest:
        raise SystemExit("proof Python source content differs")
    validated_bytes += count
    if validated_bytes > maximum_bytes:
        raise SystemExit("proof Python source byte limit exceeded")

actual_files = set()
actual_directories = {"."}
for current, directories, files in os.walk(root, topdown=True, followlinks=False):
    current_path = Path(current)
    for name in directories:
        path = current_path / name
        metadata = os.lstat(path)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o555
            or (metadata.st_uid, metadata.st_gid) != (0, 0)
        ):
            raise SystemExit("proof Python source directory differs")
        actual_directories.add(path.relative_to(root).as_posix())
    for name in files:
        path = current_path / name
        relative_value = path.relative_to(root).as_posix()
        if relative_value != ".inventory.json":
            actual_files.add(relative_value)
if actual_files != expected_files or actual_directories != expected_directories:
    raise SystemExit("proof Python source tree differs")
if validated_bytes != value["total_bytes"]:
    raise SystemExit("proof Python source total differs")
PY
}

prepare_contract() {
  create_control_custody
  stage_python_sources
  python_sources_valid
  [[ -x /usr/bin/python3 && -x "${BACKEND_BOOTSTRAP_UV}" ]]
  [[ "$(/usr/bin/python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" == 3.12 ]]
  /usr/bin/python3 -m venv --copies "${BACKEND_RUNTIME}"
  (
    cd "${REPOSITORY_ROOT}/backend"
    UV_PROJECT_ENVIRONMENT="${BACKEND_RUNTIME}" \
      "${BACKEND_BOOTSTRAP_UV}" sync --frozen --extra dev
  )
  install -d -m 0700 -o "${OWNER_UID}" -g "${DOCKER_GID}" "${ART_ROOT}" "${SERVICE_ROOT}" "${WRAPPER_WORK}"
  chown "${OWNER_UID}:${DOCKER_GID}" "${ART_ROOT}" "${SERVICE_ROOT}" "${WRAPPER_WORK}"
  chmod 0700 "${ART_ROOT}" "${SERVICE_ROOT}" "${WRAPPER_WORK}"
  [[ -x "${SERVICE_BINARY}" ]]
  setpriv --reuid "${OWNER_UID}" --regid "${DOCKER_GID}" --clear-groups \
    sh -c 'test -x "$1"; test -x "$2"; test -r "$3"; test -r "$4"; test -d "$5"; : >"$6"; : >"$7"; : >"$8"; rm -f "$6" "$7" "$8"' sh \
    "${SERVICE_BINARY}" "${DOCKER_WRAPPER}" "${EXECUTE_POST}" "${MATRIX_BUILDER}" "${PACKAGE}" \
    "${WRAPPER_WORK}/owner-write-probe" "${SERVICE_ROOT}/owner-write-probe" \
    "${ART_ROOT}/owner-write-probe"
  setpriv --reuid "${OWNER_UID}" --regid "${DOCKER_GID}" --clear-groups \
    env HOME="${STATE_ROOT}" PYTHONPATH="${BACKEND_SOURCE}" \
    "${BACKEND_PYTHON}" -c \
    'import jsonschema; from app.modules.artifacts.preparation import ArtifactScratchManager'
  "${BACKEND_PYTHON}" "${SCRIPT_DIR}/prepare_contract.py" \
    --facts "${RAW_DIR}/image-facts.json" --cache-root "${CACHE_ROOT}" \
    --material-root "${ART_ROOT}" --socket "${SOCKET_PATH}" \
    --docker-wrapper "${DOCKER_WRAPPER}" --service-config "${SERVICE_CONFIG}" \
    --contract "${RAW_DIR}/contract.json" --inventory "${RAW_DIR}/cache-inventory.json" \
    --sandbox-uid "${OWNER_UID}" --sandbox-gid "${DOCKER_GID}"
  chown "${OWNER_UID}:${DOCKER_GID}" "${SERVICE_CONFIG}" "${RAW_DIR}/contract.json" "${RAW_DIR}/cache-inventory.json"
  chmod 0400 "${SERVICE_CONFIG}"
  chmod 0600 "${RAW_DIR}/contract.json" "${RAW_DIR}/cache-inventory.json"
}

prepare_tool_evidence() {
  local xfs_package
  xfs_package="$(find "${RUNNER_TEMP_ROOT}" -maxdepth 1 -type f -name "xfsprogs_${XFS_PROGS_VERSION}_amd64.deb" -print -quit)"
  [[ -n "${xfs_package}" ]]
  XFS_PACKAGE_SHA="$(sha256sum "${xfs_package}" | cut -d' ' -f1)" \
  XFS_INSTALLED="$(dpkg-query -W -f='${Version}' xfsprogs)" \
  DOCKER_VERSION="$(docker version --format '{{.Client.Version}}/{{.Server.Version}}')" \
  RUNSC_VERSION="$("${STATE_ROOT}/tools/runsc" --version | head -1)" \
  RUSTC_VERSION="$(rustc --version)" CARGO_VERSION="$(cargo --version)" \
  BACKEND_PYTHON_VERSION="$("${BACKEND_PYTHON}" --version)" \
  CRANE_VERSION_ACTUAL="$("${CRANE_BINARY}" version)" \
  CRANE_BINARY_SHA="$(sha256sum "${CRANE_BINARY}" | cut -d' ' -f1)" \
  CRANE_ARCHIVE_SHA="$(sha256sum "${CRANE_ARCHIVE}" | cut -d' ' -f1)" \
  python3 - "${RAW_DIR}/tool-versions.json" <<'PY'
import json
import os
import platform
import subprocess
import sys

value = {
    "backend_python": os.environ["BACKEND_PYTHON_VERSION"],
    "cargo": os.environ["CARGO_VERSION"],
    "crane": os.environ["CRANE_VERSION_ACTUAL"],
    "crane_archive_sha256": os.environ["CRANE_ARCHIVE_SHA"],
    "crane_binary_sha256": os.environ["CRANE_BINARY_SHA"],
    "docker": os.environ["DOCKER_VERSION"],
    "findmnt": subprocess.check_output(["findmnt", "--version"], text=True).splitlines()[0],
    "kernel": platform.release(),
    "losetup": subprocess.check_output(["losetup", "--version"], text=True).strip(),
    "mkfs_xfs": subprocess.check_output(["mkfs.xfs", "-V"], text=True, stderr=subprocess.STDOUT).strip(),
    "runsc": os.environ["RUNSC_VERSION"],
    "rustc": os.environ["RUSTC_VERSION"],
    "xfs_package_sha256": os.environ["XFS_PACKAGE_SHA"],
    "xfsprogs_package": os.environ["XFS_INSTALLED"],
    "xfs_quota": subprocess.check_output(["xfs_quota", "-V"], text=True, stderr=subprocess.STDOUT).strip(),
}
with open(sys.argv[1], "x", encoding="utf-8") as stream:
    json.dump(value, stream, separators=(",", ":"), sort_keys=True)
    stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
PY
  chown "${OWNER_UID}:${DOCKER_GID}" "${RAW_DIR}/tool-versions.json"
  chmod 0600 "${RAW_DIR}/tool-versions.json"
}

prepare() {
  for command in docker git python3 cargo rustc truncate losetup mkfs.xfs mount findmnt mountpoint xfs_quota setpriv flock timeout; do
    require_command "${command}"
  done
  [[ -x "${CRANE_BINARY}" ]]
  [[ "$(sha256sum "${CRANE_ARCHIVE}" | cut -d' ' -f1)" == "${CRANE_ARCHIVE_SHA256}" ]]
  [[ "$("${CRANE_BINARY}" version)" == "${CRANE_VERSION#v}" ]]
  assert_source_head
  preflight
  prepare_filesystem
  install -d -m 0755 "${STATE_ROOT}"
  install -d -m 0700 -o "${OWNER_UID}" -g "${DOCKER_GID}" "${RAW_DIR}"
  pilot prepare
  capture_harness_boundary
  prepare_images
  quota_and_boundaries
  cargo build --locked --release --manifest-path "${REPOSITORY_ROOT}/external_checkers/Cargo.toml" \
    --package workstream-checker-service
  prepare_contract
  prepare_tool_evidence
  printf '%s\n' "${EXPECTED_HEAD}" >"${RAW_DIR}/proof-head.txt"
  chown "${OWNER_UID}:${DOCKER_GID}" "${RAW_DIR}/proof-head.txt"
  chmod 0600 "${RAW_DIR}/proof-head.txt"
  for name in argv.ndjson command-results.ndjson launches.ndjson service-interrupt.log service-complete.log; do
    install -m 0600 -o "${OWNER_UID}" -g "${DOCKER_GID}" /dev/null "${RAW_DIR}/${name}"
  done
  PYTHONPATH="${SCRIPT_DIR}" python3 -m unittest -q \
    test_verify_evidence test_runtime_proof
  PYTHONPATH="${BACKEND_SOURCE}:${PYTHON_SOURCE_ROOT}/scripts:${SCRIPT_DIR}" \
    "${BACKEND_PYTHON}" -B -m unittest -q test_execute_post_contract
  write_owned_json "${RAW_DIR}/verifier-tests.json" \
    '{"passed":true,"suites":["test_execute_post_contract","test_verify_evidence","test_runtime_proof"]}'
}

service_environment() {
  env -i \
    PATH="${PATH}" HOME="${STATE_ROOT}" \
    WS493_REAL_DOCKER="${REAL_DOCKER}" WS493_DIND_NAME="${DIND_NAME}" \
    WS493_RAW_DIR="${RAW_DIR}" WS493_WRAPPER_WORK_DIR="${WRAPPER_WORK}" \
    WS493_SERVICE_PID_FILE="${SERVICE_PID_FILE}" WS493_SERVICE_BINARY="${SERVICE_BINARY}" \
    WS493_BARRIER_ENABLE="${BARRIER_ENABLE}" WS493_BARRIER_READY="${BARRIER_READY}" \
    WS493_BARRIER_RELEASE="${BARRIER_RELEASE}" WS493_BARRIER_TOKEN="${BARRIER_TOKEN}" \
    WS493_SANDBOX_USER="${OWNER_UID}:${DOCKER_GID}" WS493_ART_ROOT="${ART_ROOT}" \
    WS493_CACHE_ROOT="${CACHE_ROOT}" \
    "$@"
}

socket_identity() {
  python3 - "${SOCKET_PATH}" 2>/dev/null <<'PY'
import os
import stat
import sys

value = os.lstat(sys.argv[1])
if not stat.S_ISSOCK(value.st_mode):
    raise SystemExit(1)
print(f"{value.st_dev}:{value.st_ino}:{value.st_ctime_ns}")
PY
}

service_health_ready() {
  run_as_owner "${BACKEND_PYTHON}" - "${SOCKET_PATH}" "${OWNER_UID}" "${DOCKER_GID}" \
    2>/dev/null <<'PY'
import json
import socket
import struct
import sys

socket_path, sandbox_uid, sandbox_gid = sys.argv[1:]
request = json.dumps(
    {
        "operation": "health",
        "protocol_version": "external_checker_service.v1",
    },
    separators=(",", ":"),
    sort_keys=True,
).encode()

def receive_exact(connection: socket.socket, byte_count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < byte_count:
        chunk = connection.recv(byte_count - len(chunks))
        if not chunk:
            raise RuntimeError("health response incomplete")
        chunks.extend(chunk)
    return bytes(chunks)

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
    # The listener is published before startup cleanup. Queue one bounded health
    # frame and require its exact receipt to prove the service has entered the
    # accept loop after cleanup, rather than treating socket bind as readiness.
    connection.settimeout(60)
    connection.connect(socket_path)
    connection.sendall(struct.pack(">I", len(request)) + request)
    response_size = struct.unpack(">I", receive_exact(connection, 4))[0]
    if not 0 < response_size <= 4096:
        raise RuntimeError("health response size invalid")
    response = json.loads(receive_exact(connection, response_size))
    if connection.recv(1):
        raise RuntimeError("health response has trailing bytes")

expected = {
    "architecture": "amd64",
    "cached_platform_manifests": 3,
    "isolation_mode": "gvisor",
    "operation": "health",
    "operating_system": "linux",
    "protocol_version": "external_checker_service.v1",
    "runtime": "runsc",
    "sandbox_gid": int(sandbox_gid),
    "sandbox_uid": int(sandbox_uid),
    "status": "ready",
}
if response != expected:
    raise RuntimeError("health response differs")
PY
}

start_service() {
  local log="$1"
  control_custody_valid
  python_sources_valid
  local prior_socket_identity
  prior_socket_identity="$(socket_identity || true)"
  rm -f "${SERVICE_PID_FILE}"
  printf 'service_start_head=%s\n' "${EXPECTED_HEAD}" >"${log}"
  chown "${OWNER_UID}:${DOCKER_GID}" "${log}"
  chmod 0600 "${log}"
  service_environment setpriv --reuid "${OWNER_UID}" --regid "${DOCKER_GID}" --clear-groups \
    sh -c 'printf "%s\n" "$$" >"$1"; exec "$2" "$3"' sh \
    "${SERVICE_PID_FILE}" "${SERVICE_BINARY}" "${SERVICE_CONFIG}" >>"${log}" 2>&1 &
  SERVICE_JOB_PID=$!
  for _ in $(seq 1 300); do
    if ! kill -0 "${SERVICE_JOB_PID}" 2>/dev/null; then
      local status=0
      wait "${SERVICE_JOB_PID}" || status=$?
      (( status != 0 )) || status=1
      printf 'ws493_matrix=service_start_failed status=%s\n' "${status}" >&2 || true
      if [[ -f "${log}" && ! -L "${log}" ]]; then
        if ! head -c 65536 "${log}" >&2; then
          printf 'ws493_matrix=service_log_read_failed\n' >&2 || true
        fi
      fi
      return "${status}"
    fi
    local current_socket_identity
    current_socket_identity="$(socket_identity || true)"
    if [[ -n "${current_socket_identity}" \
      && "${current_socket_identity}" != "${prior_socket_identity}" ]]; then
      if service_health_ready; then
        return 0
      fi
      if kill -0 "${SERVICE_JOB_PID}" 2>/dev/null; then
        printf 'ws493_matrix=service_health_readiness_failed\n' >&2 || true
        return 1
      fi
    fi
    sleep 0.2
  done
  printf 'ws493_matrix=service_socket_readiness_timeout\n' >&2 || true
  return 1
}

run_as_owner() {
  setpriv --reuid "${OWNER_UID}" --regid "${DOCKER_GID}" --clear-groups \
    env HOME="${STATE_ROOT}" PYTHONPATH="${BACKEND_SOURCE}" "$@"
}

positive_owned_absence() {
  local containers images
  containers="$(inner_docker ps -aq --no-trunc --filter 'label=workstream.owner=terminal-benchmark-checker-service-v1')"
  images="$(inner_docker image ls --no-trunc --quiet 'workstream.local/terminal-benchmark-candidate:*')"
  [[ -z "${containers}" && -z "${images}" ]]
}

report_matrix_failure() {
  python3 - "${RAW_DIR}" "${OWNER_UID}" "${DOCKER_GID}" 2>/dev/null <<'PY'
from collections import Counter
import json
import os
import stat
import sys

owner_uid = int(sys.argv[2])
owner_gid = int(sys.argv[3])
directory = os.open(
    sys.argv[1],
    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
)
directory_metadata = os.fstat(directory)
if (
    not stat.S_ISDIR(directory_metadata.st_mode)
    or stat.S_IMODE(directory_metadata.st_mode) != 0o700
    or directory_metadata.st_uid != owner_uid
    or directory_metadata.st_gid != owner_gid
):
    raise SystemExit(1)

def records(name):
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
        dir_fd=directory,
    )
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != owner_uid
            or metadata.st_gid != owner_gid
            or metadata.st_size > 1_048_576
        ):
            raise SystemExit(1)
        payload = bytearray()
        while chunk := os.read(descriptor, 65_536):
            payload.extend(chunk)
            if len(payload) > 1_048_576:
                raise SystemExit(1)
    finally:
        os.close(descriptor)
    lines = bytes(payload).decode("utf-8").splitlines()
    if len(lines) > 256:
        raise SystemExit(1)
    return [json.loads(line) for line in lines]

commands = records("command-results.ndjson")
launches = records("launches.ndjson")
arguments = records("argv.ndjson")
os.close(directory)
start_statuses = []
command_trace = []
for command in commands:
    argv = command.get("argv")
    status = command.get("status")
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(argument, str) for argument in argv)
        or type(status) is not int
    ):
        raise SystemExit(1)
    if argv[0] in {"create", "info", "inspect", "kill", "load", "ps", "rm", "start"}:
        kind = argv[0]
    elif len(argv) >= 2 and argv[0] == "image" and argv[1] in {"inspect", "ls", "rm"}:
        kind = "image_" + argv[1]
    elif len(argv) >= 2 and argv[0] == "container" and argv[1] in {"inspect", "ls"}:
        kind = "container_" + argv[1]
    else:
        raise SystemExit(1)
    command_trace.append({"kind": kind, "status": status})
    if len(argv) >= 2 and argv[0] == "start":
        start_statuses.append(status)
if len(command_trace) > 256 or len(start_statuses) > 8:
    raise SystemExit(1)
allowed_rejection_checks = {
    "bind_mount_count", "busybox_tmpfs", "cache_destination",
    "cache_read_only", "cache_source", "candidate_tar_destination",
    "candidate_tar_read_write", "candidate_tar_source", "cap_add", "cap_add_count",
    "cap_chown", "cap_dac_override", "cap_drop", "cap_fowner", "cap_sys_chroot", "cpu",
    "destinations", "kind", "memory", "mount_count", "name", "network", "pids",
    "project_destination", "project_read_only", "project_source", "read_only_root",
    "read_write", "runtime", "security", "socket_destination", "socket_source", "source",
    "storage", "tmpfs", "user",
}
launch_rejections = []
for argument in arguments:
    argv = argument.get("argv")
    if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
        raise SystemExit(1)
    if len(argv) != 1 or not argv[0].startswith("launch_rejection:"):
        continue
    parts = argv[0].split(":")
    if len(parts) != 3 or parts[1] not in {"builder", "candidate", "checker", "reference", "unknown"}:
        raise SystemExit(1)
    checks = parts[2].split(",")
    if (
        not checks
        or checks != sorted(set(checks))
        or any(check not in allowed_rejection_checks for check in checks)
    ):
        raise SystemExit(1)
    launch_rejections.append({"kind": parts[1], "failed_checks": checks})
if len(launch_rejections) > 8:
    raise SystemExit(1)
launch_kinds = Counter()
for launch in launches:
    kind = launch.get("kind")
    if kind not in {"builder", "candidate", "checker", "reference"}:
        raise SystemExit(1)
    launch_kinds[kind] += 1
print(
    "ws493_matrix_diagnostic="
    + json.dumps(
        {
            "command_trace": command_trace,
            "launch_kind_counts": dict(sorted(launch_kinds.items())),
            "launch_rejections": launch_rejections,
            "start_statuses": start_statuses,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
)
PY
}

run_matrix() {
  [[ "$(id -u)" -eq 0 ]]
  assert_source_head
  control_custody_valid
  python_sources_valid
  local event_since
  event_since="$(date +%s)"
  local control="${PROOF_PREFIX}-unowned-control"
  local approved_base
  approved_base="$(recorded_image_reference approved_base)"
  inner_docker create --pull=never --name "${control}" --runtime runsc --network none \
    --label "org.workstream.ws493.control=${RUN_ID}" "${approved_base}" true >/dev/null
  printf 'ws493_matrix=control_created\n'
  printf '%s\n' enabled >"${BARRIER_ENABLE}"
  chown "${OWNER_UID}:${DOCKER_GID}" "${BARRIER_ENABLE}"
  chmod 0600 "${BARRIER_ENABLE}"
  start_service "${RAW_DIR}/service-interrupt.log"
  printf 'ws493_matrix=interrupt_service_ready\n'
  local first_service_job="${SERVICE_JOB_PID}"
  run_as_owner "${BACKEND_PYTHON}" "${EXECUTE_POST}" \
    --contract "${RAW_DIR}/contract.json" --package "${PACKAGE}" --scratch "${ART_ROOT}" \
    --socket "${SOCKET_PATH}" --expect interrupted --output "${RAW_DIR}/interrupt.json" \
    --art-output "${RAW_DIR}/art-interrupt.json" &
  local executor_pid=$!
  printf 'ws493_matrix=interrupt_executor_started\n'
  for _ in $(seq 1 600); do
    [[ -f "${BARRIER_READY}" && ! -L "${BARRIER_READY}" ]] && break
    if ! kill -0 "${executor_pid}" 2>/dev/null; then
      local executor_status=0
      wait "${executor_pid}" || executor_status=$?
      (( executor_status != 0 )) || executor_status=1
      printf 'ws493_matrix=interrupt_executor_failed status=%s\n' \
        "${executor_status}" >&2 || true
      report_matrix_failure >&2 || \
        printf 'ws493_matrix_diagnostic=unavailable\n' >&2 || true
      return "${executor_status}"
    fi
    sleep 0.2
  done
  if [[ ! -f "${BARRIER_READY}" || -L "${BARRIER_READY}" ]]; then
    printf 'ws493_matrix=interrupt_barrier_unavailable\n' >&2 || true
    report_matrix_failure >&2 || \
      printf 'ws493_matrix_diagnostic=unavailable\n' >&2 || true
    return 1
  fi
  printf 'ws493_matrix=interrupt_barrier_ready\n'
  local service_pid wrapper_pid
  local barrier_values
  if ! barrier_values="$(python3 - "${BARRIER_READY}" "${BARRIER_TOKEN}" 2>/dev/null <<'PY'
import json, sys
value=json.load(open(sys.argv[1], encoding="utf-8"))
if value.get("token") != sys.argv[2]: raise SystemExit(1)
print(value["service_pid"], value["wrapper_pid"])
PY
)"; then
    printf 'ws493_matrix=interrupt_barrier_invalid\n' >&2 || true
    report_matrix_failure >&2 || \
      printf 'ws493_matrix_diagnostic=unavailable\n' >&2 || true
    return 1
  fi
  read -r service_pid wrapper_pid <<<"${barrier_values}"
  printf 'ws493_matrix=interrupt_barrier_valid\n'
  if [[ "${service_pid}" != "$(cat "${SERVICE_PID_FILE}" 2>/dev/null)" ]] \
    || [[ "$(readlink -f "/proc/${service_pid}/exe" 2>/dev/null)" \
      != "$(readlink -f "${SERVICE_BINARY}" 2>/dev/null)" ]]; then
    printf 'ws493_matrix=interrupt_service_identity_invalid\n' >&2 || true
    report_matrix_failure >&2 || \
      printf 'ws493_matrix_diagnostic=unavailable\n' >&2 || true
    return 1
  fi
  printf 'ws493_matrix=interrupt_service_identity_valid\n'
  if ! kill -KILL "${service_pid}" 2>/dev/null; then
    printf 'ws493_matrix=interrupt_service_kill_failed\n' >&2 || true
    report_matrix_failure >&2 || \
      printf 'ws493_matrix_diagnostic=unavailable\n' >&2 || true
    return 1
  fi
  printf 'ws493_matrix=interrupt_service_killed\n'
  wait "${first_service_job}" || true
  local interrupt_status=0
  wait "${executor_pid}" || interrupt_status=$?
  if (( interrupt_status != 0 )); then
    printf 'ws493_matrix=interrupt_executor_unwind_failed status=%s\n' \
      "${interrupt_status}" >&2 || true
    report_matrix_failure >&2 || \
      printf 'ws493_matrix_diagnostic=unavailable\n' >&2 || true
    return "${interrupt_status}"
  fi
  printf 'ws493_matrix=interrupt_executor_unwound\n'
  if [[ ! -s "${RAW_DIR}/art-interrupt.json" ]]; then
    printf 'ws493_matrix=interrupt_art_receipt_missing\n' >&2 || true
    report_matrix_failure >&2 || \
      printf 'ws493_matrix_diagnostic=unavailable\n' >&2 || true
    return 1
  fi
  printf 'ws493_matrix=interrupt_art_receipt_ready\n'
  printf '%s\n' "${BARRIER_TOKEN}" >"${BARRIER_RELEASE}"
  chown "${OWNER_UID}:${DOCKER_GID}" "${BARRIER_RELEASE}"
  chmod 0600 "${BARRIER_RELEASE}"
  for _ in $(seq 1 150); do
    kill -0 "${wrapper_pid}" 2>/dev/null || break
    sleep 0.2
  done
  if kill -0 "${wrapper_pid}" 2>/dev/null; then
    printf 'ws493_matrix=interrupt_wrapper_release_failed\n' >&2 || true
    report_matrix_failure >&2 || \
      printf 'ws493_matrix_diagnostic=unavailable\n' >&2 || true
    return 1
  fi
  printf 'ws493_matrix=interrupt_wrapper_released\n'
  rm -f "${BARRIER_ENABLE}" "${BARRIER_READY}" "${BARRIER_RELEASE}"

  start_service "${RAW_DIR}/service-complete.log"
  printf 'ws493_matrix=complete_service_ready\n'
  local second_service_job="${SERVICE_JOB_PID}"
  if ! positive_owned_absence; then
    printf 'ws493_matrix=restart_cleanup_incomplete\n' >&2 || true
    report_matrix_failure >&2 || \
      printf 'ws493_matrix_diagnostic=unavailable\n' >&2 || true
    return 1
  fi
  printf 'ws493_matrix=restart_cleanup_complete\n'
  if [[ "$(inner_docker inspect "${control}" \
    --format '{{index .Config.Labels "org.workstream.ws493.control"}}')" != "${RUN_ID}" ]]; then
    printf 'ws493_matrix=unowned_control_invalid\n' >&2 || true
    report_matrix_failure >&2 || \
      printf 'ws493_matrix_diagnostic=unavailable\n' >&2 || true
    return 1
  fi
  printf 'ws493_matrix=unowned_control_preserved\n'
  write_owned_json "${RAW_DIR}/restart-cleanup.json" \
    '{"owned_containers_absent":true,"owned_images_absent":true,"unowned_control_preserved":true}'
  printf 'ws493_matrix=complete_executor_started\n'
  run_as_owner "${BACKEND_PYTHON}" "${EXECUTE_POST}" \
    --contract "${RAW_DIR}/contract.json" --package "${PACKAGE}" --scratch "${ART_ROOT}" \
    --socket "${SOCKET_PATH}" --expect complete --output "${RAW_DIR}/complete-result.json" \
    --art-output "${RAW_DIR}/art-complete.json"
  printf 'ws493_matrix=complete_executor_finished\n'
  positive_owned_absence
  [[ "$(inner_docker inspect "${control}" --format '{{index .Config.Labels "org.workstream.ws493.control"}}')" == "${RUN_ID}" ]]
  inner_docker rm -f -v "${control}" >/dev/null
  kill -TERM "$(cat "${SERVICE_PID_FILE}")"
  wait "${second_service_job}" || true

  local docker_events_capture="${CONTROL_ROOT}/docker-events.ndjson.capture"
  [[ ! -e "${docker_events_capture}" && ! -L "${docker_events_capture}" ]]
  (
    umask 077
    timeout 15 "${REAL_DOCKER}" exec "${DIND_NAME}" docker events \
      --since "${event_since}" --until "$(date +%s)" \
      --filter 'label=workstream.owner=terminal-benchmark-checker-service-v1' \
      --format '{{json .}}' | head -c 262144 >"${docker_events_capture}"
  )
  python3 - "${docker_events_capture}" "${RAW_DIR}" "${OWNER_UID}" "${DOCKER_GID}" <<'PY'
import os
import stat
import sys

source_path, destination_root, owner_uid, owner_gid = sys.argv[1:]
owner_uid, owner_gid = int(owner_uid), int(owner_gid)
source_metadata = os.lstat(source_path)
if (
    not stat.S_ISREG(source_metadata.st_mode)
    or stat.S_IMODE(source_metadata.st_mode) != 0o600
    or (source_metadata.st_uid, source_metadata.st_gid) != (0, 0)
    or not 0 < source_metadata.st_size <= 262_144
):
    raise SystemExit("Docker event capture identity differs")

root_metadata = os.lstat(destination_root)
if (
    not stat.S_ISDIR(root_metadata.st_mode)
    or stat.S_IMODE(root_metadata.st_mode) != 0o700
    or (root_metadata.st_uid, root_metadata.st_gid) != (owner_uid, owner_gid)
):
    raise SystemExit("evidence root identity differs")

source = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW)
root = os.open(destination_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
destination = None
try:
    opened_root = os.fstat(root)
    if (opened_root.st_dev, opened_root.st_ino) != (
        root_metadata.st_dev,
        root_metadata.st_ino,
    ):
        raise SystemExit("evidence root changed")
    destination = os.open(
        "docker-events.ndjson",
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
        0o600,
        dir_fd=root,
    )
    copied = 0
    while chunk := os.read(source, 65_536):
        copied += len(chunk)
        if copied > 262_144:
            raise SystemExit("Docker event capture is unbounded")
        view = memoryview(chunk)
        while view:
            written = os.write(destination, view)
            if written <= 0:
                raise OSError("Docker event capture copy made no progress")
            view = view[written:]
    opened_source = os.fstat(source)
    if (
        copied != source_metadata.st_size
        or (
            opened_source.st_dev,
            opened_source.st_ino,
            opened_source.st_size,
            opened_source.st_mtime_ns,
        )
        != (
            source_metadata.st_dev,
            source_metadata.st_ino,
            source_metadata.st_size,
            source_metadata.st_mtime_ns,
        )
    ):
        raise SystemExit("Docker event capture changed")
    os.fchown(destination, owner_uid, owner_gid)
    os.fchmod(destination, 0o600)
    os.fsync(destination)
finally:
    if destination is not None:
        os.close(destination)
    os.close(root)
    os.close(source)
PY
  rm -f "${docker_events_capture}"
  run_as_owner "${BACKEND_PYTHON}" "${MATRIX_BUILDER}" \
    --raw "${RAW_DIR}" --head "${EXPECTED_HEAD}" --output "${RAW_DIR}/matrix.json"
  find "${RAW_DIR}" -maxdepth 1 -type f -exec chmod 0600 {} +
  [[ -z "$(find "${RAW_DIR}" -mindepth 1 -maxdepth 1 ! -type f -print -quit)" ]]
}

stage_evidence() {
  python3 "${SCRIPT_DIR}/verify_evidence.py" stage \
    "${RAW_DIR}" "${STAGING_DIR}" "${EXPECTED_HEAD}" "${OWNER_UID}"
}

cleanup() {
  [[ "$(id -u)" -eq 0 ]]
  local control_owned=false control_safe=true
  if [[ -e "${CONTROL_ROOT}" || -L "${CONTROL_ROOT}" ]]; then
    if control_custody_valid; then
      control_owned=true
    else
      control_safe=false
      printf '%s\n' 'refusing ambiguous WS493 control root cleanup' >&2 || true
    fi
  fi
  if [[ "${control_owned}" == true && -f "${SERVICE_PID_FILE}" && ! -L "${SERVICE_PID_FILE}" ]]; then
    local pid
    pid="$(cat "${SERVICE_PID_FILE}")"
    if [[ "${pid}" =~ ^[1-9][0-9]*$ ]] && [[ -e "/proc/${pid}/exe" ]] \
      && [[ "$(readlink -f "/proc/${pid}/exe")" == "$(readlink -f "${SERVICE_BINARY}")" ]]; then
      kill -TERM "${pid}" || true
    fi
  fi
  if [[ "${control_owned}" == true && -d "${WRAPPER_WORK}" && ! -L "${WRAPPER_WORK}" ]]; then
    printf '%s\n' "${BARRIER_TOKEN}" >"${BARRIER_RELEASE}" || true
    chown "${OWNER_UID}:${DOCKER_GID}" "${BARRIER_RELEASE}" 2>/dev/null || true
  fi
  if docker inspect "${DIND_NAME}" >/dev/null 2>&1; then
    pilot cleanup
  fi
  local outer_absent=false
  docker image rm -f \
    "ws493-checker:${EXPECTED_HEAD}" \
    "ws493-registry:${EXPECTED_HEAD}" >/dev/null 2>&1 || true
  if [[ -z "$(docker ps -aq --no-trunc --filter "label=${OUTER_OWNER_LABEL}")" ]] \
    && [[ -z "$(docker ps -aq --no-trunc --filter "label=org.workstream.ws493.run=${RUN_ID}")" ]] \
    && [[ -z "$(docker image ls --quiet "ws493-checker:${EXPECTED_HEAD}")" ]] \
    && [[ -z "$(docker image ls --quiet "ws493-registry:${EXPECTED_HEAD}")" ]]; then
    outer_absent=true
  fi
  local unmounted=false detached=false deleted=false
  if mountpoint -q "${MOUNT_ROOT}"; then
    umount "${MOUNT_ROOT}"
  fi
  if ! mountpoint -q "${MOUNT_ROOT}"; then unmounted=true; fi
  if [[ -f "${LOOP_RECORD}" && ! -L "${LOOP_RECORD}" ]]; then
    local loop_device
    loop_device="$(cat "${LOOP_RECORD}")"
    if losetup "${loop_device}" >/dev/null 2>&1; then losetup -d "${loop_device}"; fi
  fi
  if [[ ! -e "${RAW_DEVICE_FILE}" ]] || [[ -z "$(losetup -j "${RAW_DEVICE_FILE}")" ]]; then detached=true; fi
  rm -f "${RAW_DEVICE_FILE}" "${LOOP_RECORD}"
  rm -f "${RUNNER_TEMP_ROOT}/xfsprogs_${XFS_PROGS_VERSION}_amd64.deb"
  rm -rf "${CRANE_ROOT}"
  rm -f "${CRANE_ARCHIVE}"
  if [[ "${control_owned}" == true ]]; then
    rm -rf "${CONTROL_ROOT}"
  fi
  rmdir "${MOUNT_ROOT}" 2>/dev/null || true
  if [[ ! -e "${RAW_DEVICE_FILE}" && ! -e "${STATE_ROOT}" ]]; then deleted=true; fi
  rm -f "${CLEANUP_RECEIPT}"
  python3 - "${CLEANUP_RECEIPT}" "${EXPECTED_HEAD}" "${outer_absent}" "${unmounted}" "${detached}" "${deleted}" <<'PY'
import json, os, sys
truth = lambda value: value == "true"
body = {
    "schema_version": "workstream.terminal_benchmark_project_checker_proof.v1",
    "head_sha": sys.argv[2],
    "dind_absent": truth(sys.argv[3]),
    "registry_absent": truth(sys.argv[3]),
    "outer_owned_resources_absent": truth(sys.argv[3]),
    "xfs_unmounted": truth(sys.argv[4]),
    "loop_detached": truth(sys.argv[5]),
    "raw_state_deleted": truth(sys.argv[6]),
}
with open(sys.argv[1], "x", encoding="utf-8") as stream:
    json.dump(body, stream, separators=(",", ":"), sort_keys=True)
    stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
PY
  chmod 0600 "${CLEANUP_RECEIPT}"
  if [[ -d "${STAGING_DIR}" ]]; then
    python3 "${SCRIPT_DIR}/verify_evidence.py" add-cleanup \
      "${STAGING_DIR}" "${CLEANUP_RECEIPT}" "${EXPECTED_HEAD}" 0
  fi
  [[ "${control_safe}" == true && "${outer_absent}" == true && "${unmounted}" == true \
    && "${detached}" == true && "${deleted}" == true \
    && ! -e "${CRANE_ROOT}" && ! -e "${CRANE_ARCHIVE}" && ! -e "${CONTROL_ROOT}" ]]
}

final_evidence() {
  python3 "${SCRIPT_DIR}/verify_evidence.py" final "${STAGING_DIR}" "${EXPECTED_HEAD}"
}

case "${ACTION}" in
  preflight) assert_source_head; preflight ;;
  prepare) prepare ;;
  run) run_matrix ;;
  stage) stage_evidence ;;
  cleanup) cleanup ;;
  final) final_evidence ;;
  *) echo "usage: $0 preflight|prepare|run|stage|cleanup|final" >&2; exit 64 ;;
esac
