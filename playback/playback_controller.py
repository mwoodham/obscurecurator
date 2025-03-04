import threading
import time
from typing import List, Optional
from PySide6.QtCore import QObject, Signal, Slot, QTimer, QCoreApplication

from database.schema import VideoSegment
from media_processor.segment_selector import SegmentSelector
from .playback_engine import PlaybackEngine
from .transition_manager import TransitionManager

class PlaybackController(QObject):
    """Controls the playback of segments with different modes and transitions."""
    
    # Define signals
    regenerateSequenceRequest = Signal()
    skipSegmentRequest = Signal()
    
    def __init__(self, playback_engine: PlaybackEngine, segment_selector: SegmentSelector):
        super().__init__()
        self.playback_engine = playback_engine
        self.segment_selector = segment_selector
        self.transition_manager = TransitionManager()
        
        self.current_mode = 'similar'  # Default mode
        self.current_sequence: List[VideoSegment] = []
        self.sequence_position = 0
        
        self.keep_running = False
        self.sequence_lock = threading.Lock()
        
        # Connect signals
        self.playback_engine.nextSegmentNeeded.connect(self._on_next_segment_needed)
        self.regenerateSequenceRequest.connect(self._generate_sequence)
        self.skipSegmentRequest.connect(self._skip_to_next_segment)
        
        # Create a timer for checking playback status
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._check_playback_status)
        self.status_timer.setInterval(100)  # Check every 100ms
        
        print("PlaybackController initialized")
    
    @Slot()
    def _check_playback_status(self):
        """Periodically check playback status"""
        # Check if next segment is needed
        if self.playback_engine.needs_next_segment:
            self.playback_engine.needs_next_segment = False
            self._queue_next_segment()
    
    @Slot()
    def _on_next_segment_needed(self):
        """Handle signal that next segment is needed"""
        print("Next segment needed signal received")
        self._queue_next_segment()
    
    @Slot()
    def _generate_sequence(self):
        """Generate a new sequence based on current mode."""
        print(f"Generating new sequence in {self.current_mode} mode")
        
        # Run sequence generation in a separate thread to avoid blocking UI
        gen_thread = threading.Thread(target=self._generate_sequence_thread)
        gen_thread.daemon = True
        gen_thread.start()
    
    def _generate_sequence_thread(self):
        """Thread function for generating sequence"""
        try:
            # Get current segment as seed if available
            seed = None
            with self.sequence_lock:
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
            
            # Update sequence in main thread
            if sequence:
                # Use timer to update UI safely from main thread
                QTimer.singleShot(0, lambda: self._update_sequence(sequence))
            else:
                print("Failed to generate sequence")
        except Exception as e:
            print(f"Error generating sequence: {e}")
    
    def _update_sequence(self, sequence):
        """Update the sequence in the main thread"""
        with self.sequence_lock:
            self.current_sequence = sequence
            self.sequence_position = 0
            
            print(f"Generated new sequence with {len(sequence)} segments")
            for i, segment in enumerate(sequence):
                print(f"  {i+1}. {segment.source_file.filename} [{segment.start_frame}-{segment.end_frame}]")
                print(f"  Full path: {segment.source_file.path}")
                # Verify file exists
                if not Path(segment.source_file.path).exists():
                    print(f"WARNING: File does not exist: {segment.source_file.path}")
            
            # Queue first segment
            print("Queueing first segment")
            self._queue_next_segment()
    
    @Slot()
    def _skip_to_next_segment(self):
        """Skip to the next segment."""
        print("Skipping to next segment")
        self._queue_next_segment()
    
    def _queue_next_segment(self):
        """Queue the next segment for playback."""
        with self.sequence_lock:
            if not self.current_sequence:
                print("No current sequence available")
                self.regenerateSequenceRequest.emit()
                return
                
            if self.sequence_position >= len(self.current_sequence):
                print("End of sequence reached, generating new one")
                self.regenerateSequenceRequest.emit()
                return
                
            segment = self.current_sequence[self.sequence_position]
            print(f"Queueing segment {self.sequence_position + 1}/{len(self.current_sequence)}")
            
            # Queue in playback engine
            self.playback_engine.queue_segment(segment)
            
            # Move to next segment
            self.sequence_position += 1
            
            # Process events to ensure UI updates
            QCoreApplication.processEvents()
    
    def start(self, initial_mode='similar'):
        """Start the playback controller."""
        if self.keep_running:
            return
            
        print(f"Starting playback controller in {initial_mode} mode")
        self.keep_running = True
        self.current_mode = initial_mode
        
        # Start playback engine
        self.playback_engine.start()
        
        # Start status check timer
        self.status_timer.start()
        
        # Generate initial sequence
        self.regenerateSequenceRequest.emit()
    
    def stop(self):
        """Stop the playback controller."""
        if not self.keep_running:
            return
            
        print("Stopping playback controller")
        self.keep_running = False
        
        # Stop timer
        self.status_timer.stop()
        
        # Stop playback engine
        self.playback_engine.stop()
        
        print("Playback controller stopped")
    
    def set_mode(self, mode: str):
        """Set the playback mode and regenerate sequence."""
        if mode not in ['similar', 'contrast', 'random', 'concept_chain', 'diverse']:
            print(f"Unknown mode: {mode}, using 'similar' instead")
            mode = 'similar'
            
        print(f"Setting playback mode to: {mode}")
        self.current_mode = mode
        
        # Generate new sequence with new mode
        self.regenerateSequenceRequest.emit()
    
    def skip_segment(self):
        """Skip to the next segment."""
        self.skipSegmentRequest.emit()
    
    def show_playback_window(self):
        """Show the playback window."""
        print("Showing playback window")
        self.playback_engine.show()