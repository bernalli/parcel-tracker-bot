#!/usr/bin/env bash
# Regenerate cities1000.tsv — the offline geocoder dataset.
#
# Source: GeoNames "cities1000" dump (all populated places with population > 1000),
# so small towns geocode (e.g. Lurago Marinone ~2.5k inhabitants), not just the
# >15k cities of the old cities15000 set.
#
# Output is the 6-column TSV the Geocoder expects:
#   name <tab> asciiname <tab> alternatenames <tab> lat <tab> lng <tab> country_code
#
# Rows are sorted by population DESCENDING so the bare-name index (lookups without a
# country) resolves the prominent same-named city — e.g. "Roma" -> Rome, IT instead of
# Roma, AU; "New York" -> NYC instead of a Ukrainian hamlet.
set -euo pipefail
cd "$(dirname "$0")"

curl -sSL -o /tmp/cities1000.zip https://download.geonames.org/export/dump/cities1000.zip
unzip -o /tmp/cities1000.zip cities1000.txt -d /tmp

# GeoNames geoname columns: 2=name 3=asciiname 4=alternatenames 5=lat 6=lng 9=cc 15=population
awk -F'\t' 'BEGIN{OFS="\t"} {print $15, $2, $3, $4, $5, $6, $9}' /tmp/cities1000.txt \
  | sort -t "$(printf '\t')" -k1,1 -nr \
  | cut -f2- > cities1000.tsv

echo "wrote cities1000.tsv ($(wc -l < cities1000.tsv) cities, $(du -h cities1000.tsv | cut -f1))"
