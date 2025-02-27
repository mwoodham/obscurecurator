import os
import time
import pickle
import threading
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any

import config
from .file_watcher import FileWatcher
from .segment_processor import VideoSegmentProcessor
from .segment_selector import SegmentSelector
from database.schema import MediaFile, VideoSegment, ProcessingCheckpoint, ProcessingStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(config.DATA_DIR, "processor.log")),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("processor_manager")

class ProcessorManager:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.segment_processor = VideoSegmentProcessor(db_manager)
        self.file_watcher = FileWatcher(self.process_file)
        
        # Add processing queue and thread management
        self.processing_queue = []
        self.processing_lock = threading.Lock()
        self.is_processing = False
        self.current_processing_thread = None
        self.stop_requested = False
        
        # Progress tracking
        self.total_files = 0
        self.processed_files = 0
        self.current_file_progress = 0.0
        
        logger.info("ProcessorManager initialized")
    
    def process_file(self, file_path):
        """Queue a file for processing."""
        with self.processing_lock:
            # Check if file is already in queue
            if str(file_path) in [str(f) for f in self.processing_queue]:
                logger.info(f"File already in processing queue: {file_path}")
                return
            
            # Add to queue
            self.processing_queue.append(file_path)
            logger.info(f"Added file to processing queue: {file_path}")
            
            # Start processing thread if not already running
            if not self.is_processing:
                self._start_processing_thread()
    
    def process_all(self):
        """Process all files in the media directory."""
        logger.info("Starting processing of all files in media directory")
        
        # Scan for existing files first
        self.file_watcher.scan_existing()
        
        # Now start the processing thread if it's not already running
        with self.processing_lock:
            if not self.is_processing:
                self._start_processing_thread()
    
    def _start_processing_thread(self):
        """Start the background processing thread."""
        self.is_processing = True
        self.stop_requested = False
        self.current_processing_thread = threading.Thread(target=self._processing_thread)
        self.current_processing_thread.daemon = True
        self.current_processing_thread.start()
        logger.info("Started processing thread")
    
    def _processing_thread(self):
        """Main processing thread that processes files in the queue."""
        try:
            # Count total files for progress tracking
            with self.processing_lock:
                self.total_files = len(self.processing_queue)
                self.processed_files = 0
            
            while not self.stop_requested:
                # Get next file to process
                file_path = None
                with self.processing_lock:
                    if not self.processing_queue:
                        self.is_processing = False
                        break
                    file_path = self.processing_queue.pop(0)
                
                if file_path:
                    # Process the file with error handling
                    try:
                        self._process_file_safe(file_path)
                    except Exception as e:
                        logger.error(f"Error processing file {file_path}: {str(e)}", exc_info=True)
                    
                    # Update progress
                    with self.processing_lock:
                        self.processed_files += 1
                        self.current_file_progress = 0.0
        except Exception as e:
            logger.error(f"Error in processing thread: {str(e)}", exc_info=True)
            with self.processing_lock:
                self.is_processing = False
    
    def _process_file_safe(self, file_path):
        """Process a file with comprehensive error handling and checkpointing."""
        file_path = Path(file_path)
        logger.info(f"Processing file: {file_path}")
        
        # Get database session
        session = self.db_manager.get_session()
        
        try:
            # Check if file already exists in database
            media_file = session.query(MediaFile).filter_by(path=str(file_path)).first()
            
            # If file is new, create a record
            if not media_file:
                media_file = MediaFile(
                    path=str(file_path),
                    filename=file_path.name,
                    processing_status=ProcessingStatus.PENDING
                )
                session.add(media_file)
                session.commit()
                logger.info(f"Created new media file record for: {file_path}")
            
            # If file is already fully processed, skip
            elif media_file.processing_status == ProcessingStatus.COMPLETED:
                logger.info(f"File already fully processed, skipping: {file_path}")
                return
            
            # If file was previously failed, reset status to retry
            elif media_file.processing_status == ProcessingStatus.FAILED:
                logger.info(f"Retrying previously failed file: {file_path}")
                media_file.processing_status = ProcessingStatus.PENDING
                media_file.last_error = None
                session.commit()
            
            # Start processing
            media_file.processing_status = ProcessingStatus.IN_PROGRESS
            media_file.processing_started_at = datetime.utcnow()
            session.commit()
            
            # Process in stages with checkpoints
            
            # 1. Scene Detection Stage
            if not media_file.scene_detection_complete:
                try:
                    self._run_scene_detection(media_file, session, file_path)
                    media_file.scene_detection_complete = True
                    media_file.scene_detection_progress = 100.0
                    session.commit()
                    logger.info(f"Scene detection completed for: {file_path}")
                except Exception as e:
                    self._handle_processing_error(media_file, session, 
                                                "scene_detection", str(e))
                    raise
            
            # 2. Feature Extraction Stage
            if media_file.scene_detection_complete and not media_file.features_extraction_complete:
                try:
                    self._run_feature_extraction(media_file, session, file_path)
                    media_file.features_extraction_complete = True
                    media_file.feature_extraction_progress = 100.0
                    session.commit()
                    logger.info(f"Feature extraction completed for: {file_path}")
                except Exception as e:
                    self._handle_processing_error(media_file, session, 
                                                "feature_extraction", str(e))
                    raise
            
            # Mark as fully processed if all stages complete
            if media_file.scene_detection_complete and media_file.features_extraction_complete:
                media_file.processing_status = ProcessingStatus.COMPLETED
                media_file.processed = True  # For backward compatibility
                media_file.processing_completed_at = datetime.utcnow()
                session.commit()
                logger.info(f"All processing completed for: {file_path}")
            
        except Exception as e:
            logger.error(f"Error during file processing: {str(e)}", exc_info=True)
            session.rollback()
            # Final error handling at the file level
            try:
                media_file = session.query(MediaFile).filter_by(path=str(file_path)).first()
                if media_file:
                    media_file.processing_status = ProcessingStatus.FAILED
                    media_file.last_error = str(e)[:500]  # Limit error length
                    media_file.error_count += 1
                    session.commit()
            except:
                logger.error("Could not update file status after error", exc_info=True)
        finally:
            session.close()
    
    def _run_scene_detection(self, media_file, session, file_path):
        """Run scene detection with checkpointing."""
        # Check if we have a checkpoint to resume from
        checkpoint = session.query(ProcessingCheckpoint).filter_by(
            media_file_id=media_file.id, 
            checkpoint_type='scene_detection'
        ).order_by(ProcessingCheckpoint.frame_number.desc()).first()
        
        resume_frame = 0
        scenes_so_far = []
        
        if checkpoint and checkpoint.checkpoint_data:
            try:
                checkpoint_data = pickle.loads(checkpoint.checkpoint_data)
                resume_frame = checkpoint.frame_number
                scenes_so_far = checkpoint_data.get('scenes', [])
                logger.info(f"Resuming scene detection from frame {resume_frame} with {len(scenes_so_far)} scenes detected so far")
            except Exception as e:
                logger.warning(f"Could not load checkpoint data: {e}", exc_info=True)
        
        # Run scene detection with resume capability
        scenes = self.segment_processor.detect_scenes(
            file_path, 
            start_frame=resume_frame,
            existing_scenes=scenes_so_far,
            progress_callback=lambda frame, total, scenes_detected: self._update_scene_progress(
                media_file, session, frame, total, scenes_detected
            )
        )
        
        # Create segments from detected scenes
        self.segment_processor.create_segments_from_scenes(media_file, session, scenes, file_path)
    
    def _update_scene_progress(self, media_file, session, current_frame, total_frames, scenes):
        """Update scene detection progress and save checkpoint."""
        try:
            # Calculate progress percentage
            progress = (current_frame / total_frames) * 100 if total_frames > 0 else 0
            
            # Update file progress
            media_file.scene_detection_progress = progress
            self.current_file_progress = progress * 0.6  # Scene detection is 60% of total progress
            
            # Create checkpoint every 5% or when scenes are detected
            if current_frame % max(1, total_frames // 20) == 0 or len(scenes) > 0:
                # Store the serialized scenes
                checkpoint_data = {
                    'scenes': scenes
                }
                
                # Create or update checkpoint
                checkpoint = ProcessingCheckpoint(
                    media_file_id=media_file.id,
                    checkpoint_type='scene_detection',
                    frame_number=current_frame,
                    checkpoint_data=pickle.dumps(checkpoint_data)
                )
                session.add(checkpoint)
                
                # Log progress
                logger.info(f"Scene detection progress: {progress:.1f}% - Frame {current_frame}/{total_frames} - {len(scenes)} scenes")
            
            # Commit changes
            session.commit()
            
        except Exception as e:
            logger.warning(f"Failed to update scene progress: {e}", exc_info=True)
    
    def _run_feature_extraction(self, media_file, session, file_path):
        """Run feature extraction for all segments."""
        # Get all segments that need feature extraction
        segments = session.query(VideoSegment).filter_by(
            source_file_id=media_file.id,
            features_extracted=False
        ).all()
        
        total_segments = len(segments)
        if total_segments == 0:
            logger.info(f"No segments found for feature extraction: {file_path}")
            return
        
        # Process each segment
        for i, segment in enumerate(segments):
            if self.stop_requested:
                logger.info("Processing stopped by user request")
                break
                
            try:
                logger.info(f"Extracting features for segment {i+1}/{total_segments}: {segment.start_frame}-{segment.end_frame}")
                
                # Mark segment as in progress
                segment.processing_status = ProcessingStatus.IN_PROGRESS
                segment.processing_started_at = datetime.utcnow()
                session.commit()
                
                # Extract features
                self.segment_processor.extract_segment_features(segment, session, file_path)
                
                # Mark segment as done
                segment.processing_status = ProcessingStatus.COMPLETED
                segment.features_extracted = True
                segment.processed = True  # For backward compatibility
                segment.processing_completed_at = datetime.utcnow()
                session.commit()
                
                # Update progress
                progress = ((i + 1) / total_segments) * 100
                media_file.feature_extraction_progress = progress
                self.current_file_progress = 60 + (progress * 0.4)  # Feature extraction is 40% of total progress
                session.commit()
                
                logger.info(f"Feature extraction progress: {progress:.1f}% - Segment {i+1}/{total_segments}")
                
            except Exception as e:
                logger.error(f"Error extracting features for segment: {e}", exc_info=True)
                segment.processing_status = ProcessingStatus.FAILED
                segment.last_error = str(e)[:500]
                segment.error_count += 1
                session.commit()
    
    def _handle_processing_error(self, media_file, session, stage, error_msg):
        """Handle errors during processing stages."""
        try:
            media_file.last_error = f"{stage}: {error_msg}"[:500]
            media_file.error_count += 1
            session.commit()
            logger.error(f"Error in {stage} for {media_file.filename}: {error_msg}")
        except Exception as e:
            logger.error(f"Failed to record error: {e}", exc_info=True)
    
    def get_processing_status(self):
        """Get the current processing status."""
        with self.processing_lock:
            return {
                'is_processing': self.is_processing,
                'queue_length': len(self.processing_queue),
                'processed_files': self.processed_files,
                'total_files': self.total_files,
                'current_file_progress': self.current_file_progress,
                'overall_progress': (self.processed_files / self.total_files * 100) if self.total_files > 0 else 0
            }
    
    def stop_processing(self):
        """Request to stop processing after current file."""
        logger.info("Stop processing requested")
        self.stop_requested = True
    
    def resume_failed(self):
        """Queue all failed files for reprocessing."""
        session = self.db_manager.get_session()
        try:
            failed_files = session.query(MediaFile).filter_by(
                processing_status=ProcessingStatus.FAILED
            ).all()
            
            for file in failed_files:
                self.process_file(file.path)
            
            logger.info(f"Queued {len(failed_files)} failed files for reprocessing")
            return len(failed_files)
        finally:
            session.close()
    
    def start_watcher(self):
        """Start the file watcher."""
        logger.info("Starting file watcher")
        self.file_watcher.start()