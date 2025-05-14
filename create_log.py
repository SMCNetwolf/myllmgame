import os
import datetime
import logging
from google.cloud import storage
from google.cloud.logging_v2.handlers import CloudLoggingHandler
import google.cloud.logging
from config import VERBOSE, GCS_BUCKET_NAME, bucket  

# Initialize Google Cloud Logging client
client = google.cloud.logging.Client()
handler = CloudLoggingHandler(client, name="myllmgame")
logger = logging.getLogger("myllmgame")
logger.setLevel(logging.DEBUG if VERBOSE else logging.INFO)
logger.addHandler(handler)

# Local file logging
os.makedirs("log", exist_ok=True)
log_filename = os.path.join('log',f"{datetime.datetime.now().strftime('%Y-%m-%d')}_session.log")
file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(logging.DEBUG if VERBOSE else logging.INFO)
logger.addHandler(file_handler)

def create_log(message, force_log=False):
    """Log a message to Google Cloud Logging, local file, and upload to GCS if configured.
    
    Args:
        message (str): The message to log.
        force_log (bool): If True, log the message even if VERBOSE is False (at INFO level).
    """
    timestamp = datetime.datetime.now()
    log_message = f"{timestamp}: {message}"
    
    # Log to Google Cloud Logging and local file
    if force_log:
        logger.info(log_message)
    elif VERBOSE:
        logger.debug(log_message)
    else:
        logger.info(log_message)
    
    # Upload the log file to GCS
    if bucket:
        try:
            blob = bucket.blob(f"log/{os.path.basename(log_filename)}")
            blob.upload_from_filename(log_filename)
            if VERBOSE:
                logger.debug(f"CREATE_LOG: Uploaded {log_filename} to gs://{GCS_BUCKET_NAME}/log/{os.path.basename(log_filename)}")
        except Exception as e:
            logger.error(f"\n\nCREATE_LOG: Error uploading log to GCS: {str(e)}\n\n")

def clean_old_logs():
    """Delete local log files from previous days, keeping the current day's log."""
    log_dir = "log"
    if not os.path.exists(log_dir):
        if VERBOSE:
            create_log("CLEAN_OLD_LOGS: Log directory does not exist, no cleanup needed")
        return

    current_date = datetime.datetime.now().strftime('%Y-%m-%d')
    for filename in os.listdir(log_dir):
        if filename.endswith("_session.log"):
            file_date = filename.split('_')[0]
            if file_date != current_date:
                file_path = os.path.join(log_dir, filename)
                try:
                    os.remove(file_path)
                    if VERBOSE:
                        create_log(f"CLEAN_OLD_LOGS: Deleted old log file {file_path}")
                except Exception as e:
                    create_log(f"\n\nCLEAN_OLD_LOGS: Error deleting {file_path}: {str(e)}\n\n")
            else:
                if VERBOSE:
                    create_log(f"CLEAN_OLD_LOGS: Kept current log file {filename}")
