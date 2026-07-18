#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

expected_jar_sha="89948f14c93756c7a3fb7b69078ff37e8489fd79dd430c582b931e2f65358690"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-0}"

: "${PLANTUML_JAR:?Set PLANTUML_JAR to PlantUML 1.2026.6}"
printf '%s  %s\n' "$expected_jar_sha" "$PLANTUML_JAR" | sha256sum -c -
java -jar "$PLANTUML_JAR" -version | grep -F "PlantUML version 1.2026.6"

mkdir -p images

convert_diagram() {
  local source="$1"
  local target="$2"
  local rendered
  rendered="$(mktemp "${target%.png}.tmp.XXXXXX.png")"
  convert -background white -density 180 "$source" -resize '2400x2400>' "$rendered"
  if [[ -f "$target" ]] && compare -metric AE "$rendered" "$target" null: >/dev/null 2>&1; then
    rm -f "$rendered"
  else
    mv "$rendered" "$target"
  fi
}

render_plantuml() {
  java -jar "$PLANTUML_JAR" "$@"
}

case "${1:-}" in
  "") ;;
  --review-context)
    pushd ../diagrams >/dev/null
    render_plantuml -tsvg -o rendered \
      backend_v01_components.puml \
      workstream_v01_container.puml
    popd >/dev/null
    convert_diagram ../diagrams/rendered/backend_v01_components.svg images/backend_v01_components.png
    convert_diagram ../diagrams/rendered/workstream_v01_container.svg images/workstream_v01_container.png
    ;;
  --all)
    pushd ../diagrams >/dev/null
    render_plantuml -tsvg -o rendered \
      workstream_context.puml \
      workstream_v01_container.puml \
      backend_v01_components.puml \
      future_identity_payment_reputation.puml
    popd >/dev/null
    convert_diagram ../diagrams/rendered/workstream_context.svg images/workstream_context.png
    convert_diagram ../diagrams/rendered/workstream_v01_container.svg images/workstream_v01_container.png
    convert_diagram ../diagrams/rendered/backend_v01_components.svg images/backend_v01_components.png
    convert_diagram ../diagrams/rendered/future_identity_payment_reputation.svg images/future_identity_payment_reputation.png
    ;;
  *)
    echo "usage: $0 [--review-context|--all]" >&2
    exit 2
    ;;
esac

render_plantuml -tpng task_lifecycle_sequence.puml
mogrify -strip task_lifecycle_sequence.png
mv task_lifecycle_sequence.png images/task_lifecycle_sequence.png

pandoc workstream_architecture_brief.md \
  --standalone \
  --from markdown+raw_html \
  --pdf-engine=weasyprint \
  --pdf-engine-opt=--pdf-identifier=57532d5245562d3030312d3031 \
  --pdf-engine-opt=--full-fonts \
  --css brief.css \
  --metadata title="Workstream Architecture Brief" \
  --resource-path=".:images" \
  --output workstream_architecture_brief.pdf

echo "Rendered docs/architecture_brief/workstream_architecture_brief.pdf"
