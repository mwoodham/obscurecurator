from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey, Text, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class MediaFile(Base):
    __tablename__ = 'media_files'
    
    id = Column(Integer, primary_key=True)
    path = Column(String, unique=True, nullable=False)
    filename = Column(String, nullable=False)
    duration = Column(Float)
    width = Column(Integer)
    height = Column(Integer)
    fps = Column(Float)  # Added FPS for accurate playback
    has_audio = Column(Boolean, default=False)
    processed = Column(Boolean, default=False)
    
    segments = relationship("VideoSegment", back_populates="source_file")
    
    def __repr__(self):
        return f"<MediaFile(filename='{self.filename}')>"

class VideoSegment(Base):  # Renamed from Clip to VideoSegment
    __tablename__ = 'video_segments'
    
    id = Column(Integer, primary_key=True)
    source_file_id = Column(Integer, ForeignKey('media_files.id'))
    start_frame = Column(Integer, nullable=False)  # Store frame numbers instead of times
    end_frame = Column(Integer, nullable=False)    # for precise seeking
    duration = Column(Float, nullable=False)       # Keep duration for convenience
    scene_score = Column(Float)                    # Store scene detection score
    processed = Column(Boolean, default=False)
    
    source_file = relationship("MediaFile", back_populates="segments")
    features = relationship("SegmentFeature", back_populates="segment")
    
    def __repr__(self):
        return f"<VideoSegment(source='{self.source_file.filename}', start={self.start_frame}, end={self.end_frame})>"

class SegmentFeature(Base):  # Renamed from ClipFeature
    __tablename__ = 'segment_features'
    
    id = Column(Integer, primary_key=True)
    segment_id = Column(Integer, ForeignKey('video_segments.id'))
    feature_type = Column(String, nullable=False)  # e.g., 'visual', 'audio', 'semantic'
    feature_name = Column(String, nullable=False)  # e.g., 'clip_embedding', 'color_histogram'
    feature_value = Column(LargeBinary)  # Serialized feature data
    frame_number = Column(Integer)  # Store which frame this feature came from
    
    segment = relationship("VideoSegment", back_populates="features")
    
    def __repr__(self):
        return f"<SegmentFeature(segment_id={self.segment_id}, type='{self.feature_type}', name='{self.feature_name}')>"

class Tag(Base):
    __tablename__ = 'tags'
    
    id = Column(Integer, primary_key=True)
    segment_id = Column(Integer, ForeignKey('video_segments.id'))
    tag_type = Column(String, nullable=False)  # e.g., 'object', 'action', 'scene'
    tag_value = Column(String, nullable=False)
    confidence = Column(Float)
    
    segment = relationship("VideoSegment")
    
    def __repr__(self):
        return f"<Tag(value='{self.tag_value}', confidence={self.confidence})>"