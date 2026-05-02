#!/bin/bash
cd "$(dirname "$0")/../backend"
python -m pytest tests/ -v "$@"
