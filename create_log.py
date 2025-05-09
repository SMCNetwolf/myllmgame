import os
import datetime
import logging
from google.cloud import storage
from google.cloud.logging_v2.handlers import CloudLoggingHandler
import google.cloud.logging
from app import VERBOSE  # Import global VERBOSE from app.py

# Get GCS bucket name
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
if not GCS_BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME not found in environment")

# Initialize Google Cloud Storage client
bucket = None
try:
    storage_client = storage.Client()
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    if VERBOSE:
        logging.getLogger("myllmgame").debug(f"CREATE_LOG: Initialized GCS bucket {GCS_BUCKET_NAME}")
except Exception as e:
    logging.getLogger("myllmgame").error(f"CREATE_LOG: Error initializing GCS bucket {GCS_BUCKET_NAME}: {str(e)}")

# Initialize Google Cloud Logging client
client = google.cloud.logging.Client()
handler = CloudLoggingHandler(client, name="myllmgame")
logger = logging.getLogger("myllmgame")
logger.setLevel(logging.DEBUG if VERBOSE else logging.INFO)
logger.addHandler(handler)

# Local file logging
os.makedirs("log", exist_ok=True)
log_filename = f"log/{datetime.datetime.now().strftime('%Y-%m-%d')}_session.log"
file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(logging.DEBUG if VERBOSE else logging.INFO)
logger.addHandler(file_handler)

def create_log(message):
    """Log a message to Google Cloud Logging, local file, and upload to GCS if configured."""
    timestamp = datetime.datetime.now()
    log_message = f"{timestamp}: {message}"
    
    # Log to Google Cloud Logging and local file
    if VERBOSE:
        logger.debug(log_message)
    else:
        logger.info(log_message)
    
    # Upload the log file to GCS if bucket is configured
    if bucket:
        try:
            blob = bucket.blob(f"log/{os.path.basename(log_filename)}")
            blob.upload_from_filename(log_filename)
            if VERBOSE:
                logger.debug(f"CREATE_LOG: Uploaded {log_filename} to gs://{GCS_BUCKET_NAME}/log/{os.path.basename(log_filename)}")
        except Exception as e:
            logger.error(f"CREATE_LOG: Error uploading log to GCS: {str(e)}")