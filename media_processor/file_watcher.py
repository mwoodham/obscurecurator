import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import config

class MediaFileHandler(FileSystemEventHandler):
    def __init__(self, callback):
        self.callback = callback
        self.supported_extensions = config.SUPPORTED_EXTENSIONS
    
    def on_created(self, event):
        if not event.is_directory:
            path = Path(event.src_path)
            if path.suffix.lower() in self.supported_extensions:
                # Wait a moment to ensure the file is fully written
                time.sleep(1)
                self.callback(path)
    
    def on_modified(self, event):
        # Optionally handle modifications to existing files
        pass

class FileWatcher:
    def __init__(self, new_file_callback):
        self.callback = new_file_callback
        self.observer = Observer()
        self.event_handler = MediaFileHandler(self.callback)
    
    def start(self):
        """Start watching the media directory."""
        self.observer.schedule(self.event_handler, str(config.MEDIA_DIR), recursive=True)
        self.observer.start()
        print(f"Watching directory: {config.MEDIA_DIR}")
    
    def stop(self):
        """Stop watching the media directory."""
        self.observer.stop()
        self.observer.join()
    
    def scan_existing(self):
        """Scan for existing files and process them."""
        for ext in config.SUPPORTED_EXTENSIONS:
            for file_path in config.MEDIA_DIR.glob(f"**/*{ext}"):
                self.callback(file_path)