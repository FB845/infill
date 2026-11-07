#!/bin/bash
# Builds dist/: only the public files the hosted map needs (no .env, raw/, pipeline.json, video/, scripts/).
set -e
cd "$(dirname "$0")/.."
rm -rf dist && mkdir -p dist/data/cities dist/vendor
cp index.html app.js LICENSE dist/
cp data/cities.js dist/data/ && cp data/cities/*.js dist/data/cities/
cp -R vendor/leaflet dist/vendor/
cat > dist/netlify.toml <<'TOML'
[build]
  publish = "."
  command = ""
[[headers]]
  for = "/*"
  [headers.values]
    X-Content-Type-Options = "nosniff"
    Referrer-Policy = "strict-origin-when-cross-origin"
TOML
echo "dist/ ready:"; find dist -type f | sort
