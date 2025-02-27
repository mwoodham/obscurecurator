import cv2
import numpy as np
import pickle
import logging
from pathlib import Path
import time
import os
from typing import List, Dict, Tuple, Optional, Callable, Any
from datetime import datetime

from database.schema import MediaFile, VideoSegment, SegmentFeature, Tag, ProcessingStatus
from .feature_extractor import FeatureExtractor
import config

# Configure logging
logger = logging.getLogger("segment_processor")

class VideoSegmentProcessor:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.feature_extractor = FeatureExtractor(use_gpu=config.USE_GPU)
        
        # Add processing control flags
        self.stop_requested = False
    
    def detect_scenes(self, file_path: Path, start_frame: int = 0, 
                     existing_scenes: List = None, 
                     progress_callback: Callable = None) -> List[Tuple[int, int, float]]:
        """
        Detect scene changes in a video with resumable processing.
        
        Args:
            file_path: Path to the video file
            start_frame: Frame to start processing from (for resuming)
            existing_scenes: Previously detected scenes (for resuming)
            progress_callback: Function to call with progress updates
            
        Returns:
            list: List of (start_frame, end_frame, score) tuples
        """
        file_path = Path(file_path)
        logger.info(f"Detecting scenes in {file_path.name} starting from frame {start_frame}")
        
        # Initialize scene list with existing scenes if provided
        scenes = existing_scenes or []
        
        # Open video file
        cap = cv2.VideoCapture(str(file_path))
        if not cap.isOpened():
            error_msg = f"Could not open video {file_path}"
            logger.error(error_msg)
            raise IOError(error_msg)
        
        try:
            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Initialize scene change detector
            detector = cv2.createBackgroundSubtractorMOG2(history=10, varThreshold=100)
            
            # Sample frames - checking every frame would be too slow
            # For a 30fps video, check every 5 frames (6 per second)
            sample_interval = max(1, int(fps / 6))
            
            prev_frame = None
            changes = []
            scores = []
            
            # If resuming, we need the last frame before the resume point
            if start_frame > 0 and start_frame >= sample_interval:
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame - sample_interval)
                ret, frame = cap.read()
                if ret:
                    # Convert to grayscale and resize for faster processing
                    prev_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    prev_frame = cv2.resize(prev_frame, (320, 180))
            
            # Adjust start frame to be a multiple of sample_interval
            start_frame = (start_frame // sample_interval) * sample_interval
            
            # Process frames
            for i in range(start_frame, frame_count, sample_interval):
                # Check if processing should stop
                if self.stop_requested:
                    logger.info("Scene detection stopped by request")
                    break
                
                # Set frame position
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ret, frame = cap.read()
                
                if not ret:
                    logger.warning(f"Could not read frame {i}")
                    break
                
                # Convert to grayscale and resize for faster processing
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.resize(gray, (320, 180))
                
                # Apply scene detector
                mask = detector.apply(gray)
                
                # Calculate change score (percentage of changed pixels)
                score = np.count_nonzero(mask) / mask.size
                
                # Apply detector to full frame to get accurate mask
                if prev_frame is not None:
                    # Calculate frame difference
                    frame_diff = cv2.absdiff(gray, prev_frame)
                    _, frame_diff = cv2.threshold(frame_diff, 30, 255, cv2.THRESH_BINARY)
                    
                    diff_score = np.count_nonzero(frame_diff) / frame_diff.size
                    scores.append(diff_score)
                    
                    # Detect scene changes (use a threshold)
                    if diff_score > 0.15:  # If more than 15% changed
                        changes.append((i, diff_score))
                        logger.debug(f"Scene change detected at frame {i} with score {diff_score:.3f}")
                
                prev_frame = gray
                
                # Call progress callback if provided
                if progress_callback and i % (sample_interval * 20) == 0:
                    progress_callback(i, frame_count, scenes)
            
            # Group scene changes into segments
            if not changes and not scenes:
                # If no changes detected, treat the whole video as one scene
                scenes.append((0, frame_count, 0.0))
                logger.info("No scene changes detected, treating video as a single scene")
            elif not scenes:  # Only if we don't have existing scenes
                # Add first scene from start to first change
                scenes.append((0, changes[0][0], changes[0][1]))
                
                # Add middle scenes
                for i in range(len(changes) - 1):
                    scenes.append((changes[i][0], changes[i+1][0], changes[i+1][1]))
                    
                # Add last scene
                scenes.append((changes[-1][0], frame_count, 0.0))
                
                logger.info(f"Detected {len(scenes)} scenes")
            else:
                # We have existing scenes, so we need to handle the case where we might
                # need to merge with the last existing scene
                
                # If we have changes, process them
                if changes:
                    # If the first change is after the last existing scene, we need to
                    # update the end frame of the last existing scene
                    if scenes and changes[0][0] > scenes[-1][1]:
                        scenes[-1] = (scenes[-1][0], changes[0][0], scenes[-1][2])
                        
                        # Add new scenes after the last existing scene
                        for i in range(len(changes) - 1):
                            scenes.append((changes[i][0], changes[i+1][0], changes[i+1][1]))
                        
                        # Add final scene
                        scenes.append((changes[-1][0], frame_count, 0.0))
                    else:
                        # Just append the new scenes
                        for i in range(len(changes) - 1):
                            scenes.append((changes[i][0], changes[i+1][0], changes[i+1][1]))
                        
                        if changes:
                            scenes.append((changes[-1][0], frame_count, 0.0))
                
                logger.info(f"Now have {len(scenes)} scenes total")
            
            # Final progress update
            if progress_callback:
                progress_callback(frame_count, frame_count, scenes)
            
            return scenes
            
        finally:
            cap.release()
    
    def create_segments_from_scenes(self, media_file, session, scenes, file_path):
        """
        Create database segments from detected scenes.
        
        Args:
            media_file: MediaFile database object
            session: Database session
            scenes: List of (start_frame, end_frame, score) tuples
            file_path: Path to the video file
        """
        # Open video to get properties
        cap = cv2.VideoCapture(str(file_path))
        if not cap.isOpened():
            error_msg = f"Could not open video {file_path}"
            logger.error(error_msg)
            raise IOError(error_msg)
        
        try:
            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            # Update media file metadata if it doesn't have it yet
            if not media_file.fps or not media_file.width or not media_file.height:
                media_file.fps = fps
                media_file.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                media_file.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                media_file.duration = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) / fps if fps > 0 else 0
                session.commit()
            
            # Calculate minimum and maximum segment duration in frames
            min_frames = int(config.CLIP_MIN_DURATION * fps)
            max_frames = int(config.CLIP_MAX_DURATION * fps)
            
            created_count = 0
            skipped_count = 0
            
            # Create segments
            for scene_start, scene_end, score in scenes:
                # Skip scenes that are too short
                if scene_end - scene_start < min_frames:
                    logger.debug(f"Skipping short scene: {scene_start}-{scene_end} ({scene_end - scene_start} frames)")
                    skipped_count += 1
                    continue
                
                # Check if we need to split long scenes
                if scene_end - scene_start > max_frames:
                    # Create multiple segments
                    for seg_start in range(scene_start, scene_end, max_frames):
                        seg_end = min(seg_start + max_frames, scene_end)
                        if self._create_segment(session, media_file, seg_start, seg_end, score, fps):
                            created_count += 1
                else:
                    # Create a single segment
                    if self._create_segment(session, media_file, scene_start, scene_end, score, fps):
                        created_count += 1
            
            logger.info(f"Created {created_count} segments, skipped {skipped_count} short scenes")
            
        finally:
            cap.release()
    
    def _create_segment(self, session, media_file, start_frame, end_frame, scene_score, fps):
        """Create a single video segment in the database."""
        # Check if segment already exists
        existing = session.query(VideoSegment).filter_by(
            source_file_id=media_file.id,
            start_frame=start_frame,
            end_frame=end_frame
        ).first()
        
        if existing:
            logger.debug(f"Segment already exists: {start_frame}-{end_frame}")
            return False
        
        # Create a new segment
        duration = (end_frame - start_frame) / fps if fps > 0 else 0
        segment = VideoSegment(
            source_file_id=media_file.id,
            start_frame=start_frame,
            end_frame=end_frame,
            duration=duration,
            scene_score=scene_score,
            processing_status=ProcessingStatus.PENDING,
            features_extracted=False,
            processed=False
        )
        session.add(segment)
        session.commit()
        
        logger.debug(f"Created segment: {start_frame}-{end_frame} ({duration:.2f}s)")
        return True
    
    def extract_segment_features(self, segment, session, file_path):
        """
        Extract features for a video segment.
        
        Args:
            segment: VideoSegment database object
            session: Database session
            file_path: Path to the video file
        """
        logger.info(f"Extracting features for segment {segment.id}: frames {segment.start_frame}-{segment.end_frame}")
        
        # Set sampling interval based on segment duration
        interval = max(1, int((segment.end_frame - segment.start_frame) / 5))
        
        try:
            # Extract features
            features = self.feature_extractor.extract_segment_features(
                file_path, segment.start_frame, segment.end_frame, interval
            )
            
            if not features:
                error_msg = f"Failed to extract features for segment {segment.id}"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Store CLIP embedding
            clip_data = self.feature_extractor.serialize_features(features['clip_embedding'])
            clip_feature = SegmentFeature(
                segment_id=segment.id,
                feature_type='visual',
                feature_name='clip_embedding',
                feature_value=clip_data
            )
            session.add(clip_feature)
            
            # Store color histogram
            color_data = self.feature_extractor.serialize_features(features['color_histogram'])
            color_feature = SegmentFeature(
                segment_id=segment.id,
                feature_type='visual',
                feature_name='color_histogram',
                feature_value=color_data
            )
            session.add(color_feature)
            
            # Store concept scores and create tags
            for concept, score in features['concept_scores'].items():
                if score > 50:  # Only create tags for concepts with high confidence
                    tag = Tag(
                        segment_id=segment.id,
                        tag_type='concept',
                        tag_value=concept,
                        confidence=score / 100.0
                    )
                    session.add(tag)
            
            # Add top 3 concepts as dominant tags
            top_concepts = sorted(features['concept_scores'].items(), 
                                key=lambda x: x[1], reverse=True)[:3]
            
            # Add content tags based on high-scoring concepts
            for concept, score in top_concepts:
                tag = Tag(
                    segment_id=segment.id,
                    tag_type='dominant_concept',
                    tag_value=concept,
                    confidence=score / 100.0
                )
                session.add(tag)
            
            # Commit changes
            session.commit()
            logger.info(f"Features extracted for segment {segment.id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error extracting features for segment {segment.id}: {str(e)}", exc_info=True)
            session.rollback()
            
            # Update segment status
            segment.processing_status = ProcessingStatus.FAILED
            segment.last_error = str(e)[:500]
            segment.error_count += 1
            session.commit()
            
            return False
    
    def request_stop(self):
        """Request to stop processing."""
        self.stop_requested = True
        logger.info("Stop requested for segment processor")
    
    def retry_failed_segments(self, media_file_id=None):
        """
        Retry feature extraction for failed segments.
        
        Args:
            media_file_id: Optional media file ID to limit retries to a specific file
            
        Returns:
            int: Number of segments queued for retry
        """
        session = self.db_manager.get_session()
        try:
            query = session.query(VideoSegment).filter_by(
                processing_status=ProcessingStatus.FAILED
            )
            
            if media_file_id:
                query = query.filter_by(source_file_id=media_file_id)
            
            failed_segments = query.all()
            
            # Reset status for all failed segments
            for segment in failed_segments:
                segment.processing_status = ProcessingStatus.PENDING
                segment.last_error = None
            
            session.commit()
            logger.info(f"Reset {len(failed_segments)} failed segments for retry")
            return len(failed_segments)
            
        finally:
            session.close()