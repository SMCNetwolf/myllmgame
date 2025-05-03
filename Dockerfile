FROM python:3.10-slim-buster

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV PORT=8080  # Standardize on a port variable

EXPOSE $PORT

# Use Gunicorn as the production WSGI server
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "app:app"]