#!/bin/sh
source .venv/bin/activate
# Set the PORT environment variable
export PORT=8080
# Set the FLASK_APP environment variable
export FLASK_APP=app
# Run flask in debug mode, using the specified port.
flask run --debug --port=$PORT