#!/bin/sh
source .venv/bin/activate
pip install -q python-dotenv  # Install dotenv silently if not already installed
python -c "from dotenv import load_dotenv; load_dotenv()"
# running flask and defining the app file name. In this case, html_Flask.py
python -m flask --app app run -p $PORT 8000