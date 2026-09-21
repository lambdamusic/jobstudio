#!/bin/bash
# Build the static site from the Django app and publish it to Surge.
# Replaces the old src/make-docs.py pipeline (retired 2026-09-07).
set -e

clear

echo "=================="
echo "CALLING [site-build] in 1 second..."
echo "=================="
sleep 1
./tools/site-build --clean

echo "=================="
echo "CALLING [surge] in 1 second..."
echo "=================="
sleep 1
DOMAIN="${JOBSTUDIO_SURGE_DOMAIN:-$("$PY" -c "import sys; sys.path.insert(0,'src'); import config; print(config.setting('surge_domain'))" 2>/dev/null)}"
if [ -z "$DOMAIN" ]; then
    echo "No publish target. Set surge_domain in ~/.jobstudio.ini, or \$JOBSTUDIO_SURGE_DOMAIN." >&2
    exit 1
fi
surge site/ "$DOMAIN"

echo ""
echo "=================="
echo "Completed: site/ rebuilt and published to https://$DOMAIN/"
echo "=================="
