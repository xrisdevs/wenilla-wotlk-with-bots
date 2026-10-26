#!/usr/bin/env bash
# Extract dbc/maps/vmaps/mmaps from the WoW client mounted at /client into /data.
# MMAPS: by default only the arena maps are generated (full set takes hours). Set MMAP_MAPS=all for everything.
set -euo pipefail
BIN=/opt/trinitycore/bin
MMAP_MAPS="${MMAP_MAPS:-559 562 572 617 618}"
mkdir -p /work /data && cd /work
[ -e /work/Data ] || ln -s /client/Data /work/Data
if [ ! -d /data/dbc ] || [ ! -d /data/maps ]; then
  echo "== mapextractor =="; "$BIN/mapextractor" -i /work -o /work
  mv -f /work/dbc /work/maps /data/ ; rm -rf /data/Cameras; mv -f /work/Cameras /data/ 2>/dev/null || true
fi
if [ ! -d /data/vmaps ]; then
  echo "== vmap4extractor =="; "$BIN/vmap4extractor" -d /work
  mkdir -p /work/vmaps
  echo "== vmap4assembler =="; "$BIN/vmap4assembler" /work/Buildings /work/vmaps
  mv -f /work/vmaps /data/ ; rm -rf /work/Buildings
fi
mkdir -p /data/mmaps
rm -f /work/maps /work/vmaps /work/mmaps /work/dbc; ln -s /data/dbc /work/dbc; ln -s /data/maps /work/maps; ln -s /data/vmaps /work/vmaps; ln -s /data/mmaps /work/mmaps
cd /work
if [ "$MMAP_MAPS" = "all" ]; then
  echo "== mmaps_generator (all maps) =="; "$BIN/mmaps_generator" --threads "${JOBS:-8}"
else
  for m in $MMAP_MAPS; do
    if ls /data/mmaps/$(printf '%03d' "$m")*.mmtile >/dev/null 2>&1; then echo "mmaps for map $m already present"; continue; fi
    echo "== mmaps_generator map $m =="; "$BIN/mmaps_generator" "$m" --threads "${JOBS:-8}"
  done
fi
echo "EXTRACT OK: $(date)"; du -sh /data/*
