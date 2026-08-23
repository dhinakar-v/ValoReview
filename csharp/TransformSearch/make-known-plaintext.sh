#!/usr/bin/env bash
# Build a known-plaintext set from every capture whose transform is published.
#
# The oracle's power is its coverage: two captures correctly decoded share about
# 6% of their distinct first blocks, so pooling twenty-one of them raises the
# share of an unknown build's payloads that can be recognised outright. A hit
# against this set is near-proof, because the same intersection taken with a
# transform published for the wrong build returns exactly zero.
#
# Usage: make-known-plaintext.sh <scratch-dir> <demo-dir> <output-file>
set -euo pipefail

SCRATCH="$1"
DEMOS="$2"
OUT="$3"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DECODER="$ROOT/csharp/VrfPositions/bin/Release/net10.0/vrf-positions.dll"
SEARCHER="$ROOT/csharp/TransformSearch/bin/Release/net10.0/transform-search.dll"
LIMIT="${LIMIT:-120000}"

# The census below imports from libraries/, which resolves against the repo root.
cd "$ROOT"

mkdir -p "$SCRATCH/known"
: > "$SCRATCH/known/all.txt"

# Which capture is which build, from the headless scanner rather than by
# guessing at filenames.
# Through tr, because Python prints CRLF on Windows and `read` would leave
# the carriage return on the end of every filename -- which fails as a path
# with an error naming a file that is plainly there.
python - "$DEMOS" 2>/dev/null | tr -d '\r' > "$SCRATCH/known/census.txt" <<'PY'
import sys
sys.path.insert(0, "libraries")
from pathlib import Path
from vrfhome.scan import scan
for card in scan(Path(sys.argv[1])).cards:
    if card.build in (
        "++Ares-Core+release-12.10",
        "++Ares-Core+release-12.11",
        "++Ares-Core+release-13.00",
    ):
        print(card.build.split("release-")[1], Path(card.path).name)
PY

count=0
while read -r build name; do
    count=$((count + 1))
    stem="$SCRATCH/known/${build//./}-$count"
    echo "[$count] $build $name"
    VRF_PAYLOAD_CAPTURE="$stem.jsonl" \
    VRF_PAYLOAD_CAPTURE_BRANCH="++Ares-Core+release-$build" \
    VRF_PAYLOAD_CAPTURE_LIMIT="$LIMIT" \
        dotnet "$DECODER" "$DEMOS/$name" "$stem.out.json" --hz 10             >/dev/null 2>"$SCRATCH/known/last-error.txt" || {
            # Say why, rather than only that. A run where every capture is
            # "skipped" and the reason is discarded looks like a library full of
            # broken files instead of one wrong path.
            echo "    decode failed: $(tail -n 1 "$SCRATCH/known/last-error.txt")"
            continue
        }
    dotnet "$SEARCHER" emit --corpus "$stem.jsonl" --expect "$build" --count 200000 2>/dev/null \
        | awk '{print $2}' >> "$SCRATCH/known/all.txt"
    rm -f "$stem.jsonl" "$stem.out.json"
done < "$SCRATCH/known/census.txt"

sort -u "$SCRATCH/known/all.txt" > "$OUT"
echo
echo "$(wc -l < "$SCRATCH/known/all.txt") blocks from $count captures"
echo "$(wc -l < "$OUT") distinct, written to $OUT"
