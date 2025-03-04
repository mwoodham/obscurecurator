import argparse
import sys
import os
import logging
from pathlib import Path  
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QObject

import config
from media_processor.processor_manager import ProcessorManager
from media_processor.segment_selector import SegmentSelector
from playback.playback_engine import PlaybackEngine
from playback.playback_controller import PlaybackController
from ui.main_window import MainWindow
from ui.playback_control_ui import PlaybackControlUI
from database.db_manager import DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(config.DATA_DIR, "app.log")),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("main")

def parse_args():
    parser = argparse.ArgumentParser(description='AI-Driven Media Collage System')
    parser.add_argument('--process-only', action='store_true', 
                        help='Only process media files, do not start UI')
    parser.add_argument('--playback-only', action='store_true',
                        help='Only start playback UI, do not process files')
    parser.add_argument('--media-dir', type=str, 
                        help='Path to media repository')
    parser.add_argument('--migrate', action='store_true',
                        help='Run database migration before starting')
    return parser.parse_args()

def ensure_dirs_exist():
    """Ensure required directories exist."""
    config.DATA_DIR.mkdir(exist_ok=True)
    
    # Create a logs directory
    logs_dir = config.DATA_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)

def run_migration():
    """Run database migration if requested."""
    try:
        from database.migration import migrate_database
        success = migrate_database()
        if not success:
            logger.error("Database migration failed")
            return False
        return True
    except Exception as e:
        logger.error(f"Error during migration: {e}", exc_info=True)
        return False

def main():
    args = parse_args()
    
    # Ensure directories exist
    ensure_dirs_exist()
    
    # Override media directory if provided
    if args.media_dir:
        config.MEDIA_DIR = Path(args.media_dir)
        logger.info(f"Using media directory: {config.MEDIA_DIR}")
    
    # Run database migration if requested
    if args.migrate:
        if not run_migration():
            logger.error("Exiting due to migration failure")
            sys.exit(1)
    
    # Initialize database
    db_manager = DatabaseManager()
    
    try:
        db_manager.init_db()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)
        if args.process_only:
            sys.exit(1)
        else:
            # Show error dialog if in UI mode
            app = QApplication(sys.argv)
            QMessageBox.critical(None, "Database Error", 
                                f"Failed to initialize database: {str(e)}\n\n"
                                "Try running with --migrate flag to update the database schema.")
            sys.exit(1)
    
    # Initialize processor
    processor = ProcessorManager(db_manager)
    
    if args.process_only:
        # Just process files and exit
        logger.info("Running in process-only mode")
        processor.process_all()
        # Keep running until processing is done or interrupted
        try:
            import time
            while processor.is_processing:
                time.sleep(1)
            logger.info("Processing completed")
        except KeyboardInterrupt:
            logger.info("Processing interrupted by user")
            processor.stop_processing()
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
        logger.info("Running in playback-only mode")
        playback_ui = PlaybackControlUI(playback_controller, segment_selector)
        playback_ui.show()
    else:
        # Initialize main window with all components
        logger.info("Starting full application")
        main_window = MainWindow(
            processor, 
            playback_engine, 
            playback_controller,
            segment_selector,
            db_manager  # Pass db_manager to main window
        )
        main_window.show()
    
    # Start file watcher in background if not in playback-only mode
    if not args.playback_only:
        processor.start_watcher()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()