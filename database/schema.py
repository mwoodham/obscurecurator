from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey, Text, LargeBinary, DateTime, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum
import datetime

Base = declarative_base()

class ProcessingStatus(enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SCENE_DETECTED = "scene_detected"
    FEATURES_EXTRACTED = "features_extracted"
    COMPLETED = "completed"
    FAILED = "failed"

class MediaFile(Base):
    __tablename__ = 'media_files'
    
    id = Column(Integer, primary_key=True)
    path = Column(String, unique=True, nullable=False)
    filename = Column(String, nullable=False)
    duration = Column(Float)
    width = Column(Integer)
    height = Column(Integer)
    fps = Column(Float)
    has_audio = Column(Boolean, default=False)
    
    # Enhanced processing status tracking
    processing_status = Column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING)
    scene_detection_complete = Column(Boolean, default=False)
    features_extraction_complete = Column(Boolean, default=False)
    processed = Column(Boolean, default=False)  # Kept for backward compatibility
    
    # Timestamps for tracking progress
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    
    # Processing progress metrics
    scene_detection_progress = Column(Float, default=0.0)  # 0-100%
    feature_extraction_progress = Column(Float, default=0.0)  # 0-100%
    
    # Error tracking
    last_error = Column(String, nullable=True)
    error_count = Column(Integer, default=0)
    
    segments = relationship("VideoSegment", back_populates="source_file")
    
    def __repr__(self):
        return f"<MediaFile(filename='{self.filename}', status='{self.processing_status}')>"

class VideoSegment(Base):
    __tablename__ = 'video_segments'
    
    id = Column(Integer, primary_key=True)
    source_file_id = Column(Integer, ForeignKey('media_files.id'))
    start_frame = Column(Integer, nullable=False)
    end_frame = Column(Integer, nullable=False)
    duration = Column(Float, nullable=False)
    scene_score = Column(Float)
    
    # Enhanced processing status tracking
    processing_status = Column(Enum(ProcessingStatus), default=ProcessingStatus.PENDING)
    features_extracted = Column(Boolean, default=False)
    processed = Column(Boolean, default=False)  # Kept for backward compatibility
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    
    # Error tracking
    last_error = Column(String, nullable=True)
    error_count = Column(Integer, default=0)
    
    source_file = relationship("MediaFile", back_populates="segments")
    features = relationship("SegmentFeature", back_populates="segment")
    
    def __repr__(self):
        return f"<VideoSegment(source='{self.source_file.filename}', start={self.start_frame}, end={self.end_frame}, status='{self.processing_status}')>"

# Keep the rest of the schema as is
class SegmentFeature(Base):
    __tablename__ = 'segment_features'
    
    id = Column(Integer, primary_key=True)
    segment_id = Column(Integer, ForeignKey('video_segments.id'))
    feature_type = Column(String, nullable=False)
    feature_name = Column(String, nullable=False)
    feature_value = Column(LargeBinary)
    frame_number = Column(Integer)
    
    # Add timestamps
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    segment = relationship("VideoSegment", back_populates="features")
    
    def __repr__(self):
        return f"<SegmentFeature(segment_id={self.segment_id}, type='{self.feature_type}', name='{self.feature_name}')>"

class Tag(Base):
    __tablename__ = 'tags'
    
    id = Column(Integer, primary_key=True)
    segment_id = Column(Integer, ForeignKey('video_segments.id'))
    tag_type = Column(String, nullable=False)
    tag_value = Column(String, nullable=False)
    confidence = Column(Float)
    
    # Add timestamps
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    segment = relationship("VideoSegment")
    
    def __repr__(self):
        return f"<Tag(value='{self.tag_value}', confidence={self.confidence})>"

# Add a new table to store scene detection checkpoints
class ProcessingCheckpoint(Base):
    __tablename__ = 'processing_checkpoints'
    
    id = Column(Integer, primary_key=True)
    media_file_id = Column(Integer, ForeignKey('media_files.id'))
    checkpoint_type = Column(String, nullable=False)  # 'scene_detection', 'feature_extraction'
    frame_number = Column(Integer, nullable=False)  # Last processed frame
    checkpoint_data = Column(LargeBinary, nullable=True)  # For serialized state
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    def __repr__(self):
        return f"<ProcessingCheckpoint(media_file_id={self.media_file_id}, type='{self.checkpoint_type}', frame={self.frame_number})>"