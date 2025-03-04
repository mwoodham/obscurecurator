#!/usr/bin/env python3
"""
CLI Manager for AI Media Collage System
Provides command-line tools for managing the media processing pipeline
"""

import os
import sys
import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path
from tabulate import tabulate  # You may need to install this: pip install tabulate

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from database.db_manager import DatabaseManager
from database.schema import MediaFile, VideoSegment, ProcessingStatus, ProcessingCheckpoint
from media_processor.processor_manager import ProcessorManager

def parse_args():
    parser = argparse.ArgumentParser(description="CLI Manager for AI Media Collage")
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show processing status')
    status_parser.add_argument('--all', action='store_true', help='Show all files, including completed')
    status_parser.add_argument('--failed', action='store_true', help='Show only failed files')
    status_parser.add_argument('--pending', action='store_true', help='Show only pending files')
    status_parser.add_argument('--in-progress', action='store_true', help='Show only in-progress files')
    status_parser.add_argument('--limit', type=int, default=20, help='Limit number of files shown')
    
    # File details command
    file_parser = subparsers.add_parser('file', help='Show details for a specific file')
    file_parser.add_argument('file_id', type=int, help='File ID to show details for')
    file_parser.add_argument('--segments', action='store_true', help='Show segments for the file')
    
    # Process command
    process_parser = subparsers.add_parser('process', help='Process media files')
    process_parser.add_argument('--file', type=int, help='Process specific file ID')
    process_parser.add_argument('--all', action='store_true', help='Process all pending files')
    process_parser.add_argument('--retry-failed', action='store_true', help='Retry all failed files')
    process_parser.add_argument('--reset', action='store_true', help='Reset processing status before starting')
    
    # Reset command
    reset_parser = subparsers.add_parser('reset', help='Reset processing status')
    reset_parser.add_argument('--file', type=int, help='Reset specific file ID')
    reset_parser.add_argument('--failed', action='store_true', help='Reset all failed files')
    reset_parser.add_argument('--all', action='store_true', help='Reset all files')
    reset_parser.add_argument('--force', action='store_true', help='Force reset without confirmation')
    
    # Initialize database command
    init_parser = subparsers.add_parser('init', help='Initialize or reset database')
    init_parser.add_argument('--force', action='store_true', help='Force reset without confirmation')
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up database')
    cleanup_parser.add_argument('--orphaned', action='store_true', help='Remove orphaned segments')
    cleanup_parser.add_argument('--missing', action='store_true', help='Remove entries for missing files')
    cleanup_parser.add_argument('--checkpoints', action='store_true', help='Remove old checkpoints')
    cleanup_parser.add_argument('--all', action='store_true', help='Run all cleanup operations')
    cleanup_parser.add_argument('--force', action='store_true', help='Force cleanup without confirmation')
    
    # Scan command
    scan_parser = subparsers.add_parser('scan', help='Scan media directory')
    scan_parser.add_argument('--media-dir', type=str, help='Override media directory')
    
    return parser.parse_args()

def get_status_color(status):
    """Return ANSI color code based on status."""
    if status == ProcessingStatus.COMPLETED:
        return "\033[92m"  # Green
    elif status == ProcessingStatus.IN_PROGRESS:
        return "\033[94m"  # Blue
    elif status == ProcessingStatus.FAILED:
        return "\033[91m"  # Red
    elif status == ProcessingStatus.PENDING:
        return "\033[93m"  # Yellow
    else:
        return "\033[0m"   # Default

def reset_color():
    """Reset ANSI color."""
    return "\033[0m"

def format_time_ago(timestamp):
    """Format a timestamp as a human-readable time ago string."""
    if not timestamp:
        return "Never"
    
    now = datetime.utcnow()
    delta = now - timestamp
    
    if delta < timedelta(minutes=1):
        return "Just now"
    elif delta < timedelta(hours=1):
        return f"{delta.seconds // 60} minutes ago"
    elif delta < timedelta(days=1):
        return f"{delta.seconds // 3600} hours ago"
    else:
        return f"{delta.days} days ago"

def show_status(args, db_manager):
    """Show processing status."""
    session = db_manager.get_session()
    try:
        # Build query based on filters
        query = session.query(MediaFile)
        
        if not args.all:
            if args.failed:
                query = query.filter(MediaFile.processing_status == ProcessingStatus.FAILED)
            elif args.pending:
                query = query.filter(MediaFile.processing_status == ProcessingStatus.PENDING)
            elif args.in_progress:
                query = query.filter(MediaFile.processing_status == ProcessingStatus.IN_PROGRESS)
            else:
                # By default, exclude completed files
                query = query.filter(MediaFile.processing_status != ProcessingStatus.COMPLETED)
        
        # Get total counts
        total_files = session.query(MediaFile).count()
        completed = session.query(MediaFile).filter_by(processing_status=ProcessingStatus.COMPLETED).count()
        failed = session.query(MediaFile).filter_by(processing_status=ProcessingStatus.FAILED).count()
        pending = session.query(MediaFile).filter_by(processing_status=ProcessingStatus.PENDING).count()
        in_progress = session.query(MediaFile).filter_by(processing_status=ProcessingStatus.IN_PROGRESS).count()
        
        # Order by status (in progress first, then pending, then failed, then completed)
        query = query.order_by(
            # Custom ordering by status
            MediaFile.processing_status.desc(),
            # Then by updated time
            MediaFile.updated_at.desc()
        )
        
        # Limit results
        files = query.limit(args.limit).all()
        
        # Display summary
        print("\n=== Processing Status Summary ===")
        print(f"Total Files: {total_files}")
        print(f"Completed: {completed} ({(completed/total_files*100) if total_files > 0 else 0:.1f}%)")
        print(f"Failed: {failed}")
        print(f"Pending: {pending}")
        print(f"In Progress: {in_progress}")
        print("\n")
        
        # Prepare table data
        table_data = []
        for file in files:
            status_str = f"{get_status_color(file.processing_status)}{file.processing_status.value}{reset_color()}"
            
            # Calculate overall progress
            if file.processing_status == ProcessingStatus.COMPLETED:
                progress = "100%"
            elif file.scene_detection_complete and not file.features_extraction_complete:
                # Feature extraction stage
                progress = f"Scene: 100%, Features: {file.feature_extraction_progress:.1f}%"
            elif file.scene_detection_progress > 0:
                # Scene detection stage
                progress = f"Scene: {file.scene_detection_progress:.1f}%"
            else:
                progress = "Not started"
            
            # Format updated time
            updated = format_time_ago(file.updated_at) if file.updated_at else "Never"
            
            table_data.append([
                file.id,
                file.filename,
                status_str,
                progress,
                updated
            ])
        
        # Print table
        if table_data:
            print(tabulate(
                table_data,
                headers=["ID", "Filename", "Status", "Progress", "Last Updated"],
                tablefmt="grid"
            ))
        else:
            print("No files match the specified criteria.")
        
    finally:
        session.close()

def show_file_details(args, db_manager):
    """Show details for a specific file."""
    session = db_manager.get_session()
    try:
        file = session.query(MediaFile).filter_by(id=args.file_id).first()
        if not file:
            print(f"Error: File with ID {args.file_id} not found.")
            return
        
        print("\n=== File Details ===")
        print(f"ID: {file.id}")
        print(f"Filename: {file.filename}")
        print(f"Path: {file.path}")
        print(f"Status: {get_status_color(file.processing_status)}{file.processing_status.value}{reset_color()}")
        print(f"Scene Detection: {'Complete' if file.scene_detection_complete else 'Incomplete'} ({file.scene_detection_progress:.1f}%)")
        print(f"Feature Extraction: {'Complete' if file.features_extraction_complete else 'Incomplete'} ({file.feature_extraction_progress:.1f}%)")
        print(f"Processing Started: {file.processing_started_at}")
        print(f"Processing Completed: {file.processing_completed_at}")
        print(f"Last Updated: {file.updated_at}")
        print(f"Last Error: {file.last_error or 'None'}")
        print(f"Error Count: {file.error_count}")
        
        # Get segment count
        segment_count = session.query(VideoSegment).filter_by(source_file_id=file.id).count()
        print(f"\nSegments: {segment_count}")
        
        # Show segments if requested
        if args.segments and segment_count > 0:
            segments = session.query(VideoSegment).filter_by(source_file_id=file.id).order_by(VideoSegment.start_frame).all()
            
            # Prepare table data
            table_data = []
            for segment in segments:
                status_str = f"{get_status_color(segment.processing_status)}{segment.processing_status.value}{reset_color()}"
                table_data.append([
                    segment.id,
                    f"{segment.start_frame}-{segment.end_frame}",
                    f"{segment.duration:.2f}s",
                    status_str,
                    "Yes" if segment.features_extracted else "No",
                    segment.last_error or ""
                ])
            
            print("\n=== Segments ===")
            print(tabulate(
                table_data,
                headers=["ID", "Frames", "Duration", "Status", "Features", "Last Error"],
                tablefmt="grid"
            ))
        
    finally:
        session.close()

def process_files(args, db_manager):
    """Process media files."""
    # Initialize processor
    processor = ProcessorManager(db_manager)
    
    if args.reset:
        reset_files(args, db_manager, skip_confirmation=True)
    
    session = db_manager.get_session()
    try:
        if args.file:
            # Process specific file
            file = session.query(MediaFile).filter_by(id=args.file).first()
            if not file:
                print(f"Error: File with ID {args.file} not found.")
                return
            
            print(f"Processing file: {file.filename}")
            processor.process_file(file.path)
        
        elif args.retry_failed:
            # Retry all failed files
            count = processor.resume_failed()
            print(f"Queued {count} failed files for reprocessing.")
        
        elif args.all:
            # Process all pending files
            processor.process_all()
            print("Processing all pending files.")
        
        else:
            print("Error: No processing option specified. Use --file, --all, or --retry-failed.")
            return
        
        # Wait for processing to start
        time.sleep(1)
        
        # Show status updates while processing
        try:
            while processor.is_processing:
                status = processor.get_processing_status()
                progress = status['current_file_progress']
                queue_length = status['queue_length']
                
                print(f"\rProgress: {progress:.1f}% - Queue: {queue_length} files", end="")
                
                time.sleep(1)
            
            print("\nProcessing complete or stopped.")
            
        except KeyboardInterrupt:
            print("\nProcessing interrupted. Stopping gracefully...")
            processor.stop_processing()
            
    finally:
        session.close()

def reset_files(args, db_manager, skip_confirmation=False):
    """Reset processing status."""
    if not skip_confirmation and not args.force:
        confirm = input("Are you sure you want to reset processing status? This cannot be undone. (y/n): ")
        if confirm.lower() != 'y':
            print("Reset canceled.")
            return
    
    session = db_manager.get_session()
    try:
        if args.file:
            # Reset specific file
            file = session.query(MediaFile).filter_by(id=args.file).first()
            if not file:
                print(f"Error: File with ID {args.file} not found.")
                return
            
            file.processing_status = ProcessingStatus.PENDING
            file.scene_detection_complete = False
            file.features_extraction_complete = False
            file.scene_detection_progress = 0
            file.feature_extraction_progress = 0
            file.last_error = None
            file.error_count = 0
            session.commit()
            
            # Also reset all segments for this file
            segments = session.query(VideoSegment).filter_by(source_file_id=file.id).all()
            for segment in segments:
                segment.processing_status = ProcessingStatus.PENDING
                segment.features_extracted = False
                segment.last_error = None
                segment.error_count = 0
            
            session.commit()
            print(f"Reset file: {file.filename}")
            
        elif args.failed:
            # Reset all failed files
            failed_files = session.query(MediaFile).filter_by(processing_status=ProcessingStatus.FAILED).all()
            for file in failed_files:
                file.processing_status = ProcessingStatus.PENDING
                file.last_error = None
            
            # Also reset failed segments
            failed_segments = session.query(VideoSegment).filter_by(processing_status=ProcessingStatus.FAILED).all()
            for segment in failed_segments:
                segment.processing_status = ProcessingStatus.PENDING
                segment.last_error = None
            
            session.commit()
            print(f"Reset {len(failed_files)} failed files and {len(failed_segments)} failed segments.")
            
        elif args.all:
            # Reset all files
            files = session.query(MediaFile).all()
            for file in files:
                file.processing_status = ProcessingStatus.PENDING
                file.scene_detection_complete = False
                file.features_extraction_complete = False
                file.scene_detection_progress = 0
                file.feature_extraction_progress = 0
                file.last_error = None
                file.error_count = 0
            
            # Reset all segments
            segments = session.query(VideoSegment).all()
            for segment in segments:
                segment.processing_status = ProcessingStatus.PENDING
                segment.features_extracted = False
                segment.last_error = None
                segment.error_count = 0
            
            # Remove all checkpoints
            checkpoints = session.query(ProcessingCheckpoint).delete()
            
            session.commit()
            print(f"Reset {len(files)} files and {len(segments)} segments.")
            
        else:
            print("Error: No reset option specified. Use --file, --failed, or --all.")
            
    finally:
        session.close()

def init_database(args, db_manager):
    """Initialize or reset database."""
    if not args.force:
        confirm = input("Are you sure you want to initialize/reset the database? ALL DATA WILL BE LOST. (y/n): ")
        if confirm.lower() != 'y':
            print("Database initialization canceled.")
            return
    
    # Remove existing database file
    db_path = Path(config.DB_PATH)
    if db_path.exists():
        try:
            db_path.unlink()
            print(f"Removed existing database: {db_path}")
        except Exception as e:
            print(f"Error removing database file: {e}")
            return
    
    # Initialize new database
    try:
        db_manager.init_db()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")

def cleanup_database(args, db_manager):
    """Clean up database."""
    if not args.force:
        confirm = input("Are you sure you want to clean up the database? This cannot be undone. (y/n): ")
        if confirm.lower() != 'y':
            print("Cleanup canceled.")
            return
    
    session = db_manager.get_session()
    try:
        if args.orphaned or args.all:
            # Remove segments whose source file doesn't exist
            orphaned = session.query(VideoSegment).filter(
                ~VideoSegment.source_file_id.in_(
                    session.query(MediaFile.id)
                )
            ).delete(synchronize_session='fetch')
            session.commit()
            print(f"Removed {orphaned} orphaned segments.")
        
        if args.missing or args.all:
            # Remove entries for files that no longer exist on disk
            files_to_check = session.query(MediaFile).all()
            removed_count = 0
            
            for file in files_to_check:
                if not Path(file.path).exists():
                    # Remove segments first (due to foreign key constraints)
                    session.query(VideoSegment).filter_by(source_file_id=file.id).delete()
                    # Then remove the file
                    session.delete(file)
                    removed_count += 1
            
            session.commit()
            print(f"Removed {removed_count} entries for missing files.")
        
        if args.checkpoints or args.all:
            # Keep only the most recent checkpoint for each file
            media_file_ids = session.query(MediaFile.id).all()
            
            total_removed = 0
            for (file_id,) in media_file_ids:
                # For each file, get the most recent scene detection checkpoint
                latest_scene = session.query(ProcessingCheckpoint).filter_by(
                    media_file_id=file_id,
                    checkpoint_type='scene_detection'
                ).order_by(ProcessingCheckpoint.created_at.desc()).first()
                
                if latest_scene:
                    # Delete all other scene detection checkpoints for this file
                    removed = session.query(ProcessingCheckpoint).filter(
                        ProcessingCheckpoint.media_file_id == file_id,
                        ProcessingCheckpoint.checkpoint_type == 'scene_detection',
                        ProcessingCheckpoint.id != latest_scene.id
                    ).delete()
                    total_removed += removed
            
            session.commit()
            print(f"Removed {total_removed} old checkpoints.")
        
    finally:
        session.close()

def scan_media_directory(args, db_manager):
    """Scan media directory for new files."""
    # Override media directory if provided
    if args.media_dir:
        config.MEDIA_DIR = Path(args.media_dir)
    
    print(f"Scanning media directory: {config.MEDIA_DIR}")
    
    if not config.MEDIA_DIR.exists():
        print(f"Error: Media directory does not exist: {config.MEDIA_DIR}")
        return
    
    # Initialize processor and scan
    processor = ProcessorManager(db_manager)
    
    # This will scan for existing files and add them to the database
    print("Starting scan...")
    processor.file_watcher.scan_existing()
    print("Scan complete. Use 'status' command to see results.")

def main():
    args = parse_args()
    
    # Initialize database manager
    db_manager = DatabaseManager()
    
    # Execute command
    if args.command == 'status':
        show_status(args, db_manager)
    elif args.command == 'file':
        show_file_details(args, db_manager)
    elif args.command == 'process':
        process_files(args, db_manager)
    elif args.command == 'reset':
        reset_files(args, db_manager)
    elif args.command == 'init':
        init_database(args, db_manager)
    elif args.command == 'cleanup':
        cleanup_database(args, db_manager)
    elif args.command == 'scan':
        scan_media_directory(args, db_manager)
    else:
        print("Error: No command specified. Use -h for help.")
        sys.exit(1)

if __name__ == "__main__":
    main()