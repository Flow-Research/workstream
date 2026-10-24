#!/bin/sh
set -eu
printf 'partial\n' > workspace/partial.txt
kill -TERM "$$"
