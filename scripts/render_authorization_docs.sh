#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
expected_jar_sha="89948f14c93756c7a3fb7b69078ff37e8489fd79dd430c582b931e2f65358690"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-0}"

: "${PLANTUML_JAR:?Set PLANTUML_JAR to PlantUML 1.2026.6}"
printf '%s  %s\n' "$expected_jar_sha" "$PLANTUML_JAR" | sha256sum -c -
java -jar "$PLANTUML_JAR" -version | grep -F "PlantUML version 1.2026.6"

java -jar "$PLANTUML_JAR" -tsvg -o rendered \
  "$root/docs/diagrams/workstream_context.puml" \
  "$root/docs/diagrams/workstream_v01_container.puml"
java -jar "$PLANTUML_JAR" -tpng \
  "$root/docs/architecture_brief/task_lifecycle_sequence.puml"
mv "$root/docs/architecture_brief/task_lifecycle_sequence.png" \
  "$root/docs/architecture_brief/images/task_lifecycle_sequence.png"
mogrify -strip "$root/docs/architecture_brief/images/task_lifecycle_sequence.png"

convert -background white -density 180 -strip \
  "$root/docs/diagrams/rendered/workstream_context.svg" \
  -resize '2400x2400>' \
  "$root/docs/architecture_brief/images/workstream_context.png"
convert -background white -density 180 -strip \
  "$root/docs/diagrams/rendered/workstream_v01_container.svg" \
  -resize '2400x2400>' \
  "$root/docs/architecture_brief/images/workstream_v01_container.png"

cd "$root/docs/architecture_brief"
pandoc workstream_architecture_brief.md \
  --standalone \
  --from markdown+raw_html \
  --pdf-engine=weasyprint \
  --pdf-engine-opt=--pdf-identifier=workstream-authorization-baseline-v1 \
  --css brief.css \
  --metadata title="Workstream Architecture Brief" \
  --resource-path=".:images" \
  --output workstream_architecture_brief.pdf
