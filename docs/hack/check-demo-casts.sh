#!/usr/bin/env bash
#
# Copyright 2026 The Jumpstarter Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Verify the JEP-0013 observability demo recordings exist, are asciicast v2, and
# are referenced by the demos page and the landing page. Sphinx -W cannot see
# casts referenced from JavaScript, so this is the build gate for the embedding.

set -uo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
casts_dir="$repo_root/docs/source/_static/casts"
demos_page="$repo_root/docs/source/getting-started/guides/observability-demos.md"
landing_page="$repo_root/docs/source/index.md"

casts=(
  jep-0013-phase4-driver-telemetry.cast
  jep-0013-phase5-log-scraping.cast
  jep-0013-phase6-dashboards-alerting.cast
  jep-0013-phase456-integration.cast
)

status=0
fail() { printf 'ERROR: %s\n' "$*" >&2; status=1; }

for cast in "${casts[@]}"; do
  path="$casts_dir/$cast"
  if [[ ! -f "$path" ]]; then
    fail "missing recording: docs/source/_static/casts/$cast"
    continue
  fi

  first_line=$(head -n 1 "$path")
  if ! printf '%s' "$first_line" | grep -q '"version": *2'; then
    fail "not an asciicast v2 recording: docs/source/_static/casts/$cast"
  fi
done

if [[ ! -f "$demos_page" ]]; then
  fail "missing demos page: docs/source/getting-started/guides/observability-demos.md"
else
  for cast in "${casts[@]}"; do
    grep -qF "_static/casts/$cast" "$demos_page" \
      || fail "demos page does not reference docs/source/_static/casts/$cast"
  done
fi

grep -qF "_static/casts/jep-0013-phase456-integration.cast" "$landing_page" \
  || fail "landing page does not play the combined recording"

if [[ "$status" -ne 0 ]]; then
  exit 1
fi

printf 'observability demo recordings verified\n'
