import threading
import time
import queue
from typing import List, Dict, Any, Optional

from database.schema import VideoSegment
from media_processor.segment_selector import SegmentSelector
from .playback_engine import PlaybackEngine
from .transition_manager import TransitionManager

class PlaybackController:
    """Controls the playback of segments with different modes and transitions."""
    
    def __init__(self, playback_engine: PlaybackEngine, segment_selector: SegmentSelector):
        self.playback_engine = playback_engine
        self.segment_selector = segment_selector
        self.transition_manager = TransitionManager()
        
        self.current_mode = 'similar'  # Default mode
        self.current_sequence: List[VideoSegment] = []
        self.sequence_position = 0
        
        self.keep_running = False
        self.playback_thread = None
        self.sequence_lock = threading.Lock()
        self.playback_events = queue.Queue()
        
        # Setup event handler
        self.event_thread = None
        
    def start(self, initial_mode='similar'):
        """Start the playback controller."""
        if self.playback_thread and self.playback_thread.is_alive():
            return
            
        self.keep_running = True
        self.current_mode = initial_mode
        
        # Start playback engine
        self.playback_engine.start()
        
        # Start event handler thread
        self.event_thread = threading.Thread(target=self._event_loop)
        self.event_thread.daemon = True
        self.event_thread.start()
        
        # Start playback thread
        self.playback_thread = threading.Thread(target=self._playback_loop)
        self.playback_thread.daemon = True
        self.playback_thread.start()
        
        # Load initial sequence
        self._generate_sequence()
        
        print(f"Playback controller started in {initial_mode} mode")
    
    def stop(self):
        """Stop the playback controller."""
        self.keep_running = False
        
        if self.playback_thread:
            self.playback_thread.join(timeout=2.0)
        
        if self.event_thread:
            self.event_thread.join(timeout=2.0)
        
        # Stop playback engine
        self.playback_engine.stop()
        
        print("Playback controller stopped")
    
    def set_mode(self, mode: str):
        """Set the playback mode and regenerate sequence."""
        if mode not in ['similar', 'contrast', 'random', 'concept_chain', 'diverse']:
            print(f"Unknown mode: {mode}, using 'similar' instead")
            mode = 'similar'
            
        self.current_mode = mode
        
        # Queue regenerate event
        self.playback_events.put(('regenerate', None))
        
        print(f"Playback mode set to: {mode}")
    
    def _generate_sequence(self):
        """Generate a new sequence based on current mode."""
        with self.sequence_lock:
            # Get current segment as seed if available
            seed = None
            if self.current_sequence and self.sequence_position < len(self.current_sequence):
                seed = self.current_sequence[self.sequence_position]
            
            # Generate sequence
            if self.current_mode == 'diverse':
                sequence = self.segment_selector.create_diverse_sequence(length=10)
            else:
                sequence = self.segment_selector.create_sequence(
                    mode=self.current_mode,
                    length=10,
                    seed_segment=seed
                )
            
            if sequence:
                self.current_sequence = sequence
                self.sequence_position = 0
                
                # Start playback of first segment
                self._queue_next_segment()
                
                print(f"Generated new sequence with {len(sequence)} segments")
                for i, segment in enumerate(sequence):
                    print(f"  {i+1}. {segment.source_file.filename} [{segment.start_frame}-{segment.end_frame}]")
            else:
                print("Failed to generate sequence")
    
    def _queue_next_segment(self):
        """Queue the next segment for playback."""
        with self.sequence_lock:
            if not self.current_sequence:
                return
                
            if self.sequence_position >= len(self.current_sequence):
                # End of sequence, generate new one
                self.playback_events.put(('regenerate', None))
                return
                
            segment = self.current_sequence[self.sequence_position]
            self.playback_engine.queue_segment(segment)
            self.sequence_position += 1
            
            # Pre-queue next segment if available
            if self.sequence_position < len(self.current_sequence):
                next_segment = self.current_sequence[self.sequence_position]
                self.playback_engine.next_segment = next_segment
    
    def _playback_loop(self):
        """Main playback loop."""
        while self.keep_running:
            try:
                # Check if we need to queue next segment
                if self.playback_engine.needs_next_segment:
                    self.playback_engine.needs_next_segment = False
                    self._queue_next_segment()
                
                # Sleep to avoid busy waiting
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Error in playback loop: {e}")
                time.sleep(1.0)
    
    def _event_loop(self):
        """Event handling loop."""
        while self.keep_running:
            try:
                # Wait for events
                try:
                    event, data = self.playback_events.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Handle event
                if event == 'regenerate':
                    self._generate_sequence()
                elif event == 'skip':
                    self._queue_next_segment()
                
                self.playback_events.task_done()
                
            except Exception as e:
                print(f"Error in event loop: {e}")
                time.sleep(1.0)
    
    def skip_segment(self):
        """Skip to the next segment."""
        self.playback_events.put(('skip', None))
    
    def show_playback_window(self):
        """Show the playback window."""
        self.playback_engine.display_window.show()