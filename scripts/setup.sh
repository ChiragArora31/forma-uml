#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v java >/dev/null || { echo 'Java 17+ is required. Install a JDK, then re-run setup.'; exit 1; }
command -v dot >/dev/null || { echo 'Graphviz is required. Install graphviz, then re-run setup.'; exit 1; }
command -v uv >/dev/null || { echo 'uv is required: https://docs.astral.sh/uv/getting-started/installation/'; exit 1; }
command -v npm >/dev/null || { echo 'Node.js 20+ is required.'; exit 1; }
mkdir -p .tools
expected=3629c9cd017c7f73e6450396eea0040216c7e1eef8473ce33cc1aad469dab2f9
if [ ! -f .tools/plantuml.jar ]; then
  curl -fLsS --retry 2 https://github.com/plantuml/plantuml/releases/download/v1.2026.8/plantuml-mit-1.2026.8.jar -o .tools/plantuml.jar.tmp
  mv .tools/plantuml.jar.tmp .tools/plantuml.jar
fi
if command -v sha256sum >/dev/null; then
  actual=$(sha256sum .tools/plantuml.jar | cut -d ' ' -f 1)
else
  actual=$(shasum -a 256 .tools/plantuml.jar | cut -d ' ' -f 1)
fi
[ "$actual" = "$expected" ] || { echo 'PlantUML checksum mismatch. Remove .tools/plantuml.jar and retry.'; exit 1; }
uv sync --frozen --python 3.12
npm ci --prefix frontend
npm run build --prefix frontend
printf '\nReady. Run ./scripts/start.sh, then open http://127.0.0.1:8018\n'
