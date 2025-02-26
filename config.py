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

# Playback settings
DEFAULT_TRANSITION_DURATION = 0.5  # seconds
BUFFER_SIZE = 3  # number of clips to pre-buffer

# Feature extraction settings
FEATURE_EXTRACTION_INTERVAL = 0.5  # seconds between feature extraction frames
USE_GPU = True  # Set to False if GPU is not available

# Supported file extensions
SUPPORTED_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv', '.webm']

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)