#!/usr/bin/env bash
# truthcheck — pins the facts this repo must never contradict.
# Same discipline as every other repo in the fleet: a stale number in a README is how a
# measurement tool loses the only thing it has.
set -uo pipefail
FAIL=0
say() { printf '%s\n' "$*" >&2; }

banned() {
  local pat="$1" why="$2" hits
  hits=$(grep -rniE --include='*.md' --include='*.py' -- "$pat" . 2>/dev/null \
         | grep -vE '(^\./\.git/|truthcheck|CHANGELOG)' || true)
  [ -n "$hits" ] && { say "FAIL: $why"; say "$hits"; FAIL=1; }
}
required() {
  grep -qE -- "$1" "$2" 2>/dev/null || { say "FAIL: $3 (expected /$1/ in $2)"; FAIL=1; }
}

banned 'sub-?second'            'this tool cannot measure a sub-second claim'
banned 'lowest[ -]latency'      'bare comparative with no stated comparator'
banned '99\.9 ?%'               'no uptime commitment exists'
banned 'guaranteed'             'nothing here is guaranteed'
banned 'livetennisapi\.com/docs' 'docs live at docs.livetennisapi.com'
banned 'bensynapse'             'personal handle in an org repo'

required 'MIN_SAMPLE'  benchmark/metrics.py 'the minimum-sample floor must stay'
required 'MIN_PROBES'  benchmark/metrics.py 'the availability floor must stay'
required 'throttled'   benchmark/metrics.py '429s must stay out of the availability denominator'
required 'not independent|JSB Holdings LLC' README.md 'the operator must be disclosed'
required 'not.*the delay between a point being played' README.md \
         'the README must say what these numbers are NOT'

[ "$FAIL" -ne 0 ] && { say ""; say "truthcheck FAILED"; exit 1; }
say "truthcheck: OK"
