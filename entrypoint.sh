#!/bin/bash
set -e


exec python -u -m streamlit run main.py --server.port=${PORT:-8501} --server.address=0.0.0.0