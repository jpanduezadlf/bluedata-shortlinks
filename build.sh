#!/usr/bin/env bash
set -e
pip install -r requirements.txt
python -c "from app import init_db; init_db()"
