import os
import json
from dotenv import load_dotenv
from google.cloud import storage

# Load environment variables
load_dotenv()

# Global verbose setting
VERBOSE = False  # Default value

def load_config():
    """Load configuration from .env (if VERBOSE is set) or GCS."""
    global VERBOSE
    # Check if VERBOSE is set in environment (indicates local development or explicit override)
    if 'VERBOSE' in os.environ:
        VERBOSE = os.getenv('VERBOSE', 'False').lower() == 'true'
        # Use basic print for startup logging to avoid circular import with create_log
        print(f"CONFIG: Loaded VERBOSE={VERBOSE} from environment")
    else:
        # Assume production, load from GCS
        try:
            bucket_name = os.getenv('GCS_BUCKET_NAME')
            config_path = 'config/config.json'
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(config_path)
            config_data = blob.download_as_text()
            config = json.loads(config_data)
            VERBOSE = config.get('verbose', False)
            print(f"CONFIG: Loaded config from gs://{bucket_name}/{config_path}, verbose={VERBOSE}")
        except Exception as e:
            print(f"CONFIG: Error loading config from GCS: {str(e)}")
            VERBOSE = False  # Fallback to default
            print(f"CONFIG: Fell back to VERBOSE={VERBOSE} (default)")

# Load config at startup
load_config()