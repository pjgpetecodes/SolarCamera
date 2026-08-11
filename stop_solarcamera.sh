#!/usr/bin/env bash
set -euo pipefail

pids="$(ps -eo pid=,args= | grep -E 'python(3)? -m app.main' | grep -v grep | awk '{print $1}')"

if [[ -z "${pids}" ]]; then
  echo "Solar camera app is not running."
  exit 0
fi

echo "Stopping app PID(s): ${pids}"
for pid in ${pids}; do
  kill "${pid}"
done

sleep 1
echo "Done."
