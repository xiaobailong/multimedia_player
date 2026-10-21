#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR" && '/usr/local/bin/python3' "$PROJECT_DIR/Player.py" && echo Exit status: $? && exit 1