#!/bin/sh
source .venv/bin/activate
# running flask and defining the app file name. In this case, html_Flask.py
python -m flask --app app run -p $PORT --debug