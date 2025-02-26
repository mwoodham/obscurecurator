from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import config
from .file_watcher import FileWatcher
from .segment_processor import VideoSegmentProcessor
from .segment_selector import SegmentSelector

class ProcessorManager:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.segment_processor = VideoSegmentProcessor(db_manager)
        self.file_watcher = FileWatcher(self.process_file)
        
    def process_file(self, file_path):
        self.segment_processor.process_file(file_path)
    
    def process_all(self):
        print("Processing all files in media directory")
        self.file_watcher.scan_existing()
    
    def start_watcher(self):
        print("Starting file watcher")
        self.file_watcher.start()