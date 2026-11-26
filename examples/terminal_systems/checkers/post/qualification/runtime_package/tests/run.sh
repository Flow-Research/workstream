#!/bin/sh
set -eu
test -f workspace/result.txt
test "$(cat workspace/result.txt)" = 'qualified-result'
