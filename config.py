import os
from pathlib import Path

# Base directories
PROJECT_ROOT = Path(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = PROJECT_ROOT / "data"
MEDIA_DIR = Path("/Users/Matthew/Movies/TV/Media.localized")  # Update this!
DB_PATH = DATA_DIR / "media_collage.db"

# Processing settings
CLIP_MIN_DURATION = 1.0  # seconds
CLIP_MAX_DURATION = 15.0  # seconds
PROCESS_BATCH_SIZE = 5  # number of files to process at once

# Checkpoint settings
SCENE_DETECTION_CHECKPOINT_INTERVAL = 500  # frames between checkpoints
FEATURE_EXTRACTION_CHECKPOINT_INTERVAL = 5  # segments between checkpoints

# Error handling
MAX_RETRIES = 3  # maximum number of retry attempts
ERROR_WAIT_TIME = 5  # seconds to wait after error before retry

# Playback settings
DEFAULT_TRANSITION_DURATION = 0.5  # seconds
BUFFER_SIZE = 3  # number of clips to pre-buffer

# Feature extraction settings
FEATURE_EXTRACTION_INTERVAL = 0.5  # seconds between feature extraction frames
USE_GPU = True  # Set to False if GPU is not available

# Supported file extensions
SUPPORTED_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv', '.webm']

# Logging settings
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
LOG_FILE_COUNT = 5  # Number of backup log files

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)

# Make logs directory
LOGS_DIR = DATA_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)