#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

output_dir="${1:-rendered}"
mkdir -p "$output_dir"

if command -v plantuml >/dev/null 2>&1; then
  plantuml -tsvg -o "$output_dir" ./*.puml
elif [[ -n "${PLANTUML_JAR:-}" ]]; then
  java -jar "$PLANTUML_JAR" -tsvg -o "$output_dir" ./*.puml
else
  cat >&2 <<'MSG'
PlantUML is required to render these diagrams.

Use one of:
  plantuml -tsvg -o rendered docs/diagrams/*.puml
  PLANTUML_JAR=/path/to/plantuml.jar docs/diagrams/render_plantuml.sh

The .puml files are standalone; no remote includes are required.
MSG
  exit 1
fi
