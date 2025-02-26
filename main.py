import argparse
import sys
from pathlib import Path  
from PySide6.QtWidgets import QApplication

import config
from media_processor.processor_manager import ProcessorManager
from media_processor.segment_selector import SegmentSelector
from playback.playback_engine import PlaybackEngine
from playback.playback_controller import PlaybackController
from ui.main_window import MainWindow
from ui.playback_control_ui import PlaybackControlUI
from database.db_manager import DatabaseManager

def parse_args():
    parser = argparse.ArgumentParser(description='AI-Driven Media Collage System')
    parser.add_argument('--process-only', action='store_true', 
                        help='Only process media files, do not start UI')
    parser.add_argument('--playback-only', action='store_true',
                        help='Only start playback UI, do not process files')
    parser.add_argument('--media-dir', type=str, 
                        help='Path to media repository')
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Override media directory if provided
    if args.media_dir:
        config.MEDIA_DIR = Path(args.media_dir)
    
    # Initialize database
    db_manager = DatabaseManager()
    db_manager.init_db()
    
    # Initialize processor
    processor = ProcessorManager(db_manager)
    
    if args.process_only:
        # Just process files and exit
        processor.process_all()
        return
    
    # Initialize application and UI
    app = QApplication(sys.argv)
    
    # Initialize segment selector
    segment_selector = SegmentSelector(db_manager)
    
    # Initialize playback engine
    playback_engine = PlaybackEngine(db_manager)
    
    # Initialize playback controller
    playback_controller = PlaybackController(playback_engine, segment_selector)
    
    if args.playback_only:
        # Start only the playback UI
        playback_ui = PlaybackControlUI(playback_controller, segment_selector)
        playback_ui.show()
    else:
        # Initialize main window with all components
        main_window = MainWindow(
            processor, 
            playback_engine, 
            playback_controller,
            segment_selector
        )
        main_window.show()
    
    # Start file watcher in background if not in playback-only mode
    if not args.playback_only:
        processor.start_watcher()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()