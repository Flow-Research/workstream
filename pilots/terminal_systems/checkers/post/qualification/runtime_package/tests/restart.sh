#!/bin/sh
set -eu
test -f workspace/partial.txt
printf 'qualified-result\n' > workspace/result.txt
