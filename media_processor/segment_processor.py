import cv2
import numpy as np
from pathlib import Path
import time
import os

from database.schema import MediaFile, VideoSegment, SegmentFeature, Tag
from .feature_extractor import FeatureExtractor
import config

class VideoSegmentProcessor:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.feature_extractor = FeatureExtractor(use_gpu=config.USE_GPU)
        
    def process_file(self, file_path):
        """Process a video file: identify scenes and extract features.
        
        Args:
            file_path: Path to the video file
        """
        file_path = Path(file_path)
        print(f"\nProcessing file: {file_path}")
        
        # Get database session
        session = self.db_manager.get_session()
        
        try:
            # Check if file already exists in database
            existing_file = session.query(MediaFile).filter_by(path=str(file_path)).first()
            if existing_file and existing_file.processed:
                print(f"File already processed: {file_path}")
                return
            
            # Open video file
            cap = cv2.VideoCapture(str(file_path))
            if not cap.isOpened():
                print(f"Error: Could not open video {file_path}")
                return
                
            # Get video metadata
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0
            
            has_audio = False  # Need additional library like moviepy to detect audio
            
            # Create or update media file record
            if existing_file:
                media_file = existing_file
            else:
                media_file = MediaFile(
                    path=str(file_path),
                    filename=file_path.name,
                    duration=duration,
                    width=width,
                    height=height,
                    fps=fps,
                    has_audio=has_audio,
                    processed=False
                )
                session.add(media_file)
                session.commit()
            
            # Perform scene detection
            print(f"Detecting scenes in {file_path.name}...")
            scenes = self._detect_scenes(cap, fps)
            
            # Create segments from scenes
            min_frames = int(config.CLIP_MIN_DURATION * fps)
            max_frames = int(config.CLIP_MAX_DURATION * fps)
            
            for scene_start, scene_end, score in scenes:
                # Skip scenes that are too short
                if scene_end - scene_start < min_frames:
                    continue
                    
                # Split long scenes
                if scene_end - scene_start > max_frames:
                    # Create multiple segments
                    for seg_start in range(scene_start, scene_end, max_frames):
                        seg_end = min(seg_start + max_frames, scene_end)
                        self._create_segment(
                            session, media_file, seg_start, seg_end, 
                            score, file_path, fps
                        )
                else:
                    # Create a single segment
                    self._create_segment(
                        session, media_file, scene_start, scene_end, 
                        score, file_path, fps
                    )
            
            # Mark file as processed
            media_file.processed = True
            session.commit()
            
            print(f"Completed processing file: {file_path.name}")
            cap.release()
            
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
            session.rollback()
        finally:
            session.close()
    
    def _detect_scenes(self, cap, fps):
        """Detect scene changes in a video.
        
        Args:
            cap: OpenCV VideoCapture object
            fps: Frames per second
            
        Returns:
            list: List of (start_frame, end_frame, score) tuples
        """
        # Initialize scene change detector
        detector = cv2.createBackgroundSubtractorMOG2(history=10, varThreshold=100)
        
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Sample frames - checking every frame would be too slow
        # For a 30fps video, check every 5 frames (6 per second)
        sample_interval = max(1, int(fps / 6))
        
        prev_frame = None
        changes = []
        scores = []
        
        # Process frames
        for i in range(0, frame_count, sample_interval):
            # Set frame position
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            
            if not ret:
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
            
            prev_frame = gray
            
            # Progress indication every 100 frames
            if i % (sample_interval * 100) == 0:
                print(f"Scene detection: {i}/{frame_count} frames processed")
        
        # Group scene changes into segments
        scenes = []
        
        if not changes:
            # If no changes detected, treat the whole video as one scene
            scenes.append((0, frame_count, 0.0))
        else:
            # Add first scene from start to first change
            scenes.append((0, changes[0][0], changes[0][1]))
            
            # Add middle scenes
            for i in range(len(changes) - 1):
                scenes.append((changes[i][0], changes[i+1][0], changes[i+1][1]))
                
            # Add last scene
            scenes.append((changes[-1][0], frame_count, 0.0))
        
        return scenes
    
    def _create_segment(self, session, media_file, start_frame, end_frame, 
                       scene_score, file_path, fps):
        """Create a video segment and extract its features.
        
        Args:
            session: Database session
            media_file: MediaFile object
            start_frame: Start frame number
            end_frame: End frame number
            scene_score: Scene change score
            file_path: Path to video file
            fps: Frames per second
        """
        # Check if segment already exists
        existing = session.query(VideoSegment).filter_by(
            source_file_id=media_file.id,
            start_frame=start_frame,
            end_frame=end_frame
        ).first()
        
        if existing:
            segment = existing
            print(f"Segment already exists: {start_frame}-{end_frame}")
        else:
            # Create a new segment
            duration = (end_frame - start_frame) / fps
            segment = VideoSegment(
                source_file_id=media_file.id,
                start_frame=start_frame,
                end_frame=end_frame,
                duration=duration,
                scene_score=scene_score,
                processed=False
            )
            session.add(segment)
            session.commit()
            
            print(f"Created segment: {start_frame}-{end_frame} ({duration:.2f}s)")
        
        # Skip feature extraction if already processed
        if segment.processed:
            return
            
        # Extract features
        print(f"Extracting features for segment {start_frame}-{end_frame}...")
        
        # Set sampling interval based on segment duration
        interval = max(1, int((end_frame - start_frame) / 5))
        
        features = self.feature_extractor.extract_segment_features(
            file_path, start_frame, end_frame, interval
        )
        
        if features:
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
            
            # Add top 3 concepts as tags
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
            
            # Mark segment as processed
            segment.processed = True
            session.commit()
            
            print(f"Features extracted for segment {start_frame}-{end_frame}")