import numpy as np
import random
import pickle
from sqlalchemy import func, desc, asc
from sqlalchemy.orm import joinedload
from typing import List, Dict, Tuple, Optional
import heapq
import time
import threading

from database.schema import VideoSegment, MediaFile, SegmentFeature, Tag
from .feature_extractor import FeatureExtractor

class SegmentSelector:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.feature_extractor = FeatureExtractor(use_gpu=False)  # GPU not needed for comparison
        self.last_segments = []  # Keep track of recently played segments
    
    def random_segment(self):
        """Get a random video segment with timeout protection."""
        print("Getting random segment")
        timeout_seconds = 3
        result = [None]  # Use a list to store result from the thread
        
        def query_func():
            try:
                session = self.db_manager.get_session()
                try:
                    # Only select from processed segments
                    count = session.query(VideoSegment).filter_by(processed=True).count()
                    if count == 0:
                        return None
                    
                    random_offset = random.randint(0, count - 1)
                    segment = session.query(VideoSegment)\
                        .filter_by(processed=True)\
                        .options(joinedload(VideoSegment.source_file))\
                        .offset(random_offset)\
                        .first()
                    
                    if segment:
                        self.last_segments.append(segment.id)
                        # Keep last 10 segments
                        if len(self.last_segments) > 10:
                            self.last_segments.pop(0)
                    
                    result[0] = segment
                finally:
                    session.close()
            except Exception as e:
                print(f"Error in random_segment: {e}")
        
        # Run the query in a separate thread with timeout
        query_thread = threading.Thread(target=query_func)
        query_thread.daemon = True
        query_thread.start()
        query_thread.join(timeout_seconds)
        
        if query_thread.is_alive():
            print(f"Warning: random_segment timed out after {timeout_seconds} seconds")
            # Try getting the result anyway, but don't wait
            return result[0]
        
        return result[0]
    
    def get_segment_features(self, segment_id: int, feature_type='visual', feature_name='clip_embedding'):
        """Get features for a segment."""
        session = self.db_manager.get_session()
        try:
            feature = session.query(SegmentFeature)\
                .filter_by(
                    segment_id=segment_id, 
                    feature_type=feature_type,
                    feature_name=feature_name
                )\
                .first()
            
            if not feature:
                return None
                
            return self.feature_extractor.deserialize_features(feature.feature_value)
        finally:
            session.close()
    
    def find_similar_segments(self, segment_id, feature_type='visual', 
                            feature_name='clip_embedding', limit=5, exclude_recent=True):
        """Find segments with similar features with timeout."""
        print(f"Finding similar segments to {segment_id}")
        timeout_seconds = 3
        result = [None]  # Use a list to store result from the thread
        
        def query_func():
            try:
                session = self.db_manager.get_session()
                try:
                    # Get the reference segment's features
                    ref_features = self.get_segment_features(segment_id, feature_type, feature_name)
                    
                    if ref_features is None:
                        result[0] = []
                        return
                    
                    # Get all segments
                    segments = session.query(VideoSegment)\
                        .filter_by(processed=True)\
                        .options(joinedload(VideoSegment.source_file))\
                        .filter(VideoSegment.id != segment_id)\
                        .limit(100)\
                        .all()  # Note: moved .all() to its own line
                    
                    if exclude_recent:
                        # Exclude recently played segments
                        segments = [s for s in segments if s.id not in self.last_segments]
                    
                    # Calculate similarity for each segment
                    similarities = []
                    
                    for segment in segments:
                        # Get segment features
                        features = self.get_segment_features(segment.id, feature_type, feature_name)
                        if features is None:
                            continue
                            
                        # Calculate similarity
                        if feature_name == 'clip_embedding':
                            # For CLIP embeddings, use dot product
                            similarity = np.dot(ref_features, features)
                        elif feature_name == 'color_histogram':
                            # For color histograms, use histogram intersection
                            similarity = np.minimum(ref_features, features).sum() / ref_features.sum()
                        else:
                            # Default similarity
                            similarity = 0.0
                            
                        similarities.append((segment, float(similarity)))
                    
                    # Sort by similarity (highest first)
                    similarities.sort(key=lambda x: x[1], reverse=True)
                    
                    # Return top results
                    result[0] = similarities[:limit]
                finally:
                    session.close()
            except Exception as e:
                print(f"Error in find_similar_segments: {e}")
                result[0] = []
        
        # Run the query in a separate thread with timeout
        query_thread = threading.Thread(target=query_func)
        query_thread.daemon = True
        query_thread.start()
        query_thread.join(timeout_seconds)
        
        if query_thread.is_alive():
            print(f"Warning: find_similar_segments timed out after {timeout_seconds} seconds")
            # Return an empty list if timed out
            return []
        
        return result[0] or []
    
    def find_contrasting_segments(self, segment_id: int, feature_type='visual', 
                                feature_name='clip_embedding', limit=5) -> List[Tuple[VideoSegment, float]]:
        """Find segments with contrasting features."""
        # Similar to find_similar_segments but sorts by lowest similarity
        session = self.db_manager.get_session()
        try:
            # Get the reference segment's features
            ref_features = self.get_segment_features(segment_id, feature_type, feature_name)
            
            if ref_features is None:
                return []
            
            # Get all segments
            segments = session.query(VideoSegment)\
                .filter_by(processed=True)\
                .options(joinedload(VideoSegment.source_file))\
                .filter(VideoSegment.id != segment_id)\
                .all()
            
            # Exclude recently played segments
            segments = [s for s in segments if s.id not in self.last_segments]
            
            # Calculate similarity for each segment
            results = []
            
            for segment in segments:
                # Get segment features
                features = self.get_segment_features(segment.id, feature_type, feature_name)
                if features is None:
                    continue
                    
                # Calculate similarity
                if feature_name == 'clip_embedding':
                    # For CLIP embeddings, use dot product
                    similarity = np.dot(ref_features, features)
                elif feature_name == 'color_histogram':
                    # For color histograms, use histogram intersection
                    similarity = np.minimum(ref_features, features).sum() / ref_features.sum()
                else:
                    # Default similarity
                    similarity = 0.5
                    
                # For contrasting, we want dissimilar segments
                # So we use negative similarity
                results.append((segment, -float(similarity)))
            
            # Sort by lowest similarity (highest negative similarity)
            results.sort(key=lambda x: x[1], reverse=True)
            
            # Return top results
            return [(segment, -similarity) for segment, similarity in results[:limit]]
        finally:
            session.close()
    
    def find_segments_by_tag(self, tag_value: str, tag_type='concept', limit=5) -> List[VideoSegment]:
        """Find segments with a specific tag."""
        session = self.db_manager.get_session()
        try:
            segments = session.query(VideoSegment)\
                .filter_by(processed=True)\
                .options(joinedload(VideoSegment.source_file))\
                .join(Tag)\
                .filter(Tag.tag_type == tag_type)\
                .filter(Tag.tag_value == tag_value)\
                .order_by(desc(Tag.confidence))\
                .limit(limit)\
                .all()
                
            # Exclude recently played segments
            segments = [s for s in segments if s.id not in self.last_segments]
            
            return segments
        finally:
            session.close()
    
    def find_segments_by_concept(self, concept: str, limit=5) -> List[VideoSegment]:
        """Find segments matching a specific concept."""
        return self.find_segments_by_tag(concept, tag_type='concept', limit=limit)
    
    def create_sequence(self, mode='similar', length=10, seed_segment=None, 
                    feature_type='visual', feature_name='clip_embedding'):
        """Create a sequence of segments with timeout protection."""
        print(f"Creating sequence in mode: {mode}, length: {length}")
        
        # Use a simple approach to avoid timeouts
        try:
            # Clear recent segments history if starting new sequence
            if seed_segment is None:
                self.last_segments = []
                
            # Get initial segment if not provided
            current_segment = seed_segment or self.random_segment()
            if not current_segment:
                print("No initial segment found")
                return []
                
            sequence = [current_segment]
            self.last_segments.append(current_segment.id)
            
            # Add segments up to the requested length
            attempts = 0
            max_attempts = length * 3  # Allow more attempts than segments needed
            
            while len(sequence) < length and attempts < max_attempts:
                attempts += 1
                
                # Different strategies based on mode
                if mode == 'similar':
                    # Try to find similar segment
                    similar = self.find_similar_segments(
                        current_segment.id, 
                        feature_type=feature_type, 
                        feature_name=feature_name,
                        limit=3
                    )
                    
                    if similar:
                        # Pick randomly from the similar segments
                        next_segment, _ = random.choice(similar)
                    else:
                        # Fallback to random
                        next_segment = self.random_segment()
                        if not next_segment:
                            break
                
                elif mode == 'random':
                    # Just pick a random segment
                    next_segment = self.random_segment()
                    if not next_segment:
                        break
                
                else:
                    # For other modes, just default to random for safety
                    next_segment = self.random_segment()
                    if not next_segment:
                        break
                
                # Add to sequence
                sequence.append(next_segment)
                self.last_segments.append(next_segment.id)
                current_segment = next_segment
                
                # Prevent duplicates in the sequence
                if len(self.last_segments) > 10:
                    self.last_segments.pop(0)
            
            print(f"Sequence created with {len(sequence)} segments")
            return sequence
            
        except Exception as e:
            print(f"Error creating sequence: {e}")
            return []  # Return empty list on error
        
    def get_common_tags(self, count=10) -> List[Tuple[str, int]]:
        """Get the most common tags across all segments."""
        session = self.db_manager.get_session()
        try:
            # Count occurrences of each tag
            tag_counts = session.query(
                Tag.tag_value, 
                func.count(Tag.id).label('count')
            )\
                .filter(Tag.tag_type == 'concept')\
                .group_by(Tag.tag_value)\
                .order_by(desc('count'))\
                .limit(count)\
                .all()
                
            return [(tag, count) for tag, count in tag_counts]
        finally:
            session.close()
    
    def create_diverse_sequence(self, length=10) -> List[VideoSegment]:
        """Create a diverse sequence by alternating between different modes."""
        sequence = []
        
        # Start with a random segment
        current = self.random_segment()
        if not current:
            return []
            
        sequence.append(current)
        
        # Alternate between modes
        modes = ['similar', 'contrast', 'concept_chain']
        mode_index = 0
        
        while len(sequence) < length:
            mode = modes[mode_index]
            sub_sequence = self.create_sequence(
                mode=mode,
                length=2,  # Just add a couple segments at a time
                seed_segment=current,
                feature_type='visual',
                feature_name='clip_embedding'
            )
            
            # Add new segments
            if len(sub_sequence) > 1:
                new_segments = sub_sequence[1:]  # Skip seed segment
                sequence.extend(new_segments)
                if new_segments:
                    current = new_segments[-1]
            
            # Update mode
            mode_index = (mode_index + 1) % len(modes)
            
            # If we couldn't find any segments, try a random one
            if len(sequence) == 1:
                random_segment = self.random_segment()
                if random_segment:
                    sequence.append(random_segment)
                    current = random_segment
                else:
                    break
        
        return sequence[:length]    