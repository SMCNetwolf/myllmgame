import os
import json
from dotenv import load_dotenv
from google.cloud import storage

CONFIG_PATH = os.path.join('config','config.json')
INITIAL_IMAGE_FILE_PATH = os.path.join('static', 'image', 'default_image.png')
DEFAULT_IMAGE_FILE_PATH = os.path.join('static', 'image', 'output_image.png')
ERROR_IMAGE_FILE_PATH  = os.path.join('static', 'image', 'error_image.png')
DEFAULT_AUDIO_FILE_PATH = os.path.join('static', 'audio', 'default_audio.mp3')
IMAGE_FILE_PREFIX = os.path.join('static', 'image', 'output_image')
WORLD_PATH = os.path.join('.', 'SeuMundo_L1.json')
SAVE_GAMES_PATH = os.path.join('.', 'game_saves')
TEMP_SAVES_PATH = os.path.join('temp_saves', 'last_session.json')
DB_PATH = os.path.join('database', 'users.db')

# Load environment variables if running locally
load_dotenv()

# If in production, VERBOSE is not initialized yet because there's no .env in Docker container

# Get SESSION_SECRET. It must be set in .env AND in production env variable
SESSION_SECRET = os.environ.get("SESSION_SECRET")
if not SESSION_SECRET:
    raise ValueError("SESSION_SECRET not found in environment")  

# Get TOGETHER_API_KEY. It must be set in .env AND in production env variable
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY")
if not TOGETHER_API_KEY:
    raise ValueError("TOGETHER_API_KEY not found in environment")  

# Initialize GCS client and bucket (present both locally and in production)
storage_client = None
bucket = None

# Get GCS bucket name. It must be set in .env AND in production env variable
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME") 
if not GCS_BUCKET_NAME:
    raise ValueError("GCS_BUCKET_NAME not found in environment.")

try:
    storage_client = storage.Client()
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
except Exception as e:
    # can't use create_log yet because it's not initialized
    print(f"CONFIG: Error initializing GCS bucket {GCS_BUCKET_NAME}: {str(e)}")
    raise

def load_config():
    """Load configuration from .env (if VERBOSE is set) or GCS."""
    global VERBOSE
    # Check if VERBOSE is set in environment (indicates local development)
    if 'VERBOSE' in os.environ:
        VERBOSE = os.getenv('VERBOSE', 'False').lower() == 'true'
        # Use basic print for startup logging to avoid circular import with create_log
        print(f"CONFIG: Loaded VERBOSE={VERBOSE} from development environment")
    else:
        # Assume in production, load VERBOSE from config.json in GCS
        try:
            blob = bucket.blob(CONFIG_PATH)
            config_data = blob.download_as_text()
            config = json.loads(config_data)
            VERBOSE = config.get('verbose', False)
            print(f"CONFIG: VERBOSE set to {VERBOSE} from config.json in gs://{GCS_BUCKET_NAME}/{CONFIG_PATH}, verbose={VERBOSE}")
        except Exception as e:
            print(f"CONFIG: Error loading config from GCS: {str(e)}")
            VERBOSE = False  # Fallback to default
            print(f"CONFIG: Fell back to VERBOSE={VERBOSE} (default)")

# Load config at startup to get the global VERBOSE setting
load_config()

# More configuration
MODEL = "meta-llama/Llama-3-70b-chat-hf"
IS_SAFE_MODEL = "Meta-Llama/LlamaGuard-2-8b"
IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell-Free"
MAX_SAVE = 5  # Maximum number of saved games per user    

SOUND_MAP = {
    "dialogue": "static/audio/dialogue.mp3",
    "exploration": "static/audio/exploration.mp3",
    "use_item": "static/audio/use_item.mp3",
    "combat": "static/audio/combat.mp3",
    "puzzle": "static/audio/puzzle.mp3",
    "false_ally": "static/audio/false_ally.mp3",
    "generic": "static/audio/default_audio.mp3"
}