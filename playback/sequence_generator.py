import threading
import queue
import time
from typing import List, Optional, Callable
from PySide6.QtCore import QObject, Signal, Slot, QThread

from database.schema import VideoSegment

class SequenceGeneratorWorker(QObject):
    """Worker object that generates sequences in a background thread"""
    
    # Signals
    sequenceReady = Signal(list)  # Signal emitting the generated sequence
    generationFailed = Signal(str)  # Signal for error reporting
    
    def __init__(self, segment_selector):
        super().__init__()
        self.segment_selector = segment_selector
        self.mode = 'similar'
        self.length = 10
        self.seed_segment = None
        
    @Slot()
    def generate_sequence(self):
        """Generate a sequence in the worker thread"""
        try:
            print(f"Worker: Generating sequence in mode '{self.mode}' with length {self.length}")
            
            # Choose the appropriate generation method based on mode
            if self.mode == 'diverse':
                sequence = self.segment_selector.create_diverse_sequence(length=self.length)
            else:
                sequence = self.segment_selector.create_sequence(
                    mode=self.mode,
                    length=self.length,
                    seed_segment=self.seed_segment
                )
            
            if sequence:
                print(f"Worker: Generated sequence with {len(sequence)} segments")
                self.sequenceReady.emit(sequence)
            else:
                print("Worker: No sequence could be generated")
                self.generationFailed.emit("Failed to generate sequence - no segments returned")
                
        except Exception as e:
            print(f"Worker: Error generating sequence: {str(e)}")
            self.generationFailed.emit(f"Error generating sequence: {str(e)}")

class SequenceGenerator(QObject):
    """Manages background sequence generation"""
    
    sequenceReady = Signal(list)  # Signal when a sequence is ready
    generationFailed = Signal(str)  # Signal when generation fails
    
    def __init__(self, segment_selector):
        super().__init__()
        self.segment_selector = segment_selector
        
        # Create worker and thread
        self.worker_thread = QThread()
        self.worker = SequenceGeneratorWorker(segment_selector)
        
        # Move worker to thread
        self.worker.moveToThread(self.worker_thread)
        
        # Connect signals and slots
        self.worker.sequenceReady.connect(self.sequenceReady)
        self.worker.generationFailed.connect(self.generationFailed)
        self.worker_thread.started.connect(self.worker.generate_sequence)
        
        # Start the thread
        self.worker_thread.start()
    
    def generate_sequence(self, mode='similar', length=10, seed_segment=None):
        """Request a sequence generation"""
        print(f"Requesting sequence generation in mode '{mode}' with length {length}")
        
        # Set parameters in worker
        self.worker.mode = mode
        self.worker.length = length
        self.worker.seed_segment = seed_segment
        
        # If thread is not running, start it
        if not self.worker_thread.isRunning():
            self.worker_thread.start()
        else:
            # Otherwise trigger the worker directly
            self.worker.generate_sequence()
    
    def cleanup(self):
        """Clean up resources"""
        if self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait(2000)  # Wait up to 2 seconds