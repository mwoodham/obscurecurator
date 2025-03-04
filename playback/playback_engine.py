import cv2
import queue
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from collections import OrderedDict
from PySide6.QtWidgets import QMainWindow
from PySide6.QtCore import Qt, QTimer, QObject, Signal, Slot, QThread, QCoreApplication
from PySide6.QtGui import QPainter, QImage
import numpy as np

@dataclass
class VideoBuffer:
    cap: cv2.VideoCapture
    last_access: float
    ref_count: int

@dataclass
class SegmentInfo:
    segment: any  # VideoSegment
    file_path: str
    start_frame: int
    end_frame: int
    duration: float

class VideoPlayerWorker(QObject):
    """Worker for playing video segments"""
    frameReady = Signal(np.ndarray)  # Signal to send frames to display
    segmentFinished = Signal()  # Signal when segment finishes
    error = Signal(str)  # Signal for errors
    
    def __init__(self):
        super().__init__()
        self.file_path = None
        self.start_frame = 0
        self.end_frame = 0
        self.running = False
    
    def set_segment(self, segment_info):
        """Set the segment to play"""
        self.file_path = segment_info.file_path
        self.start_frame = segment_info.start_frame
        self.end_frame = segment_info.end_frame
        self.segment_info = segment_info
    
    @Slot()
    def play(self):
        """Play the assigned segment"""
        if not self.file_path:
            self.error.emit("No segment assigned")
            return
        
        self.running = True
        print(f"Worker: Playing {self.file_path} from frame {self.start_frame} to {self.end_frame}")
        
        try:
            # Check if file exists
            if not Path(self.file_path).exists():
                print(f"Worker: File does not exist: {self.file_path}")
                self.error.emit(f"File does not exist: {self.file_path}")
                return
                
            cap = cv2.VideoCapture(self.file_path)
            
            if not cap.isOpened():
                print(f"Worker: Could not open video: {self.file_path}")
                self.error.emit(f"Could not open video: {self.file_path}")
                return
            
            # Set starting position
            cap.set(cv2.CAP_PROP_POS_FRAMES, self.start_frame)
            
            # Get frame rate
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 24  # Default if cannot determine
            
            frame_delay = 1.0 / fps
            frame_count = 0
            
            while self.running:
                # Read frame
                ret, frame = cap.read()
                
                if not ret:
                    print(f"Worker: End of file reached for {self.file_path}")
                    break
                
                # Check if we've reached the end frame
                current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                if current_frame >= self.end_frame:
                    print(f"Worker: End frame reached: {current_frame} >= {self.end_frame}")
                    break
                
                # Emit the frame to the main thread
                self.frameReady.emit(frame)
                frame_count += 1
                
                # Process events to ensure UI updates
                QCoreApplication.processEvents()
                
                # Log progress occasionally
                if frame_count % 30 == 0:
                    print(f"Worker: Played {frame_count} frames from {self.file_path}")
                
                # Control playback speed
                time.sleep(frame_delay)
            
            cap.release()
            print(f"Worker: Playback complete for {self.file_path}")
            self.segmentFinished.emit()
            
        except Exception as e:
            print(f"Worker: Error playing segment: {e}")
            self.error.emit(str(e))
            self.segmentFinished.emit()
        
        self.running = False

class DisplayWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Media Collage Output")
        self.setFixedSize(1280, 720)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        
        # Initialize frame buffer
        self.current_frame = None
        
        # Create refresh timer to ensure continuous UI updates
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_ui)
        self.refresh_timer.start(16)  # ~60fps refresh rate
        
        print("Display window initialized")
    
    def refresh_ui(self):
        """Force a UI refresh"""
        if self.current_frame is not None:
            self.update()
    
    @Slot(np.ndarray)
    def updateFrame(self, frame):
        """Update the current frame - called via signal/slot"""
        if frame is not None:
            # Process frame
            frame = cv2.resize(frame, (1280, 720))
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.current_frame = rgb_frame
            self.update()  # Request a repaint
            # Process events to ensure immediate update
            QCoreApplication.processEvents()
    
    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            
            if self.current_frame is not None:
                # Create QImage from frame data
                image = QImage(self.current_frame.data, 1280, 720, 
                             1280 * 3, QImage.Format_RGB888)
                painter.drawImage(0, 0, image)
            else:
                painter.fillRect(self.rect(), Qt.black)
                
        except Exception as e:
            print(f"Error in paint event: {e}")

    def mousePressEvent(self, event):
        """Handle mouse press events for dragging"""
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """Handle mouse move events for dragging"""
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

class PlaybackEngine(QObject):
    """Enhanced playback engine using QThread model"""
    nextSegmentNeeded = Signal()  # Signal when next segment is needed
    
    def __init__(self, db_manager):
        super().__init__()
        self.db_manager = db_manager
        self.current_segment = None
        self.next_segment = None
        self.needs_next_segment = False
        
        # Create worker and thread
        self.player_thread = QThread()
        self.player_worker = VideoPlayerWorker()
        self.player_worker.moveToThread(self.player_thread)
        
        # Create display window
        self.display_window = DisplayWindow()
        
        # Connect signals
        self.player_worker.frameReady.connect(self.display_window.updateFrame)
        self.player_worker.segmentFinished.connect(self._on_segment_finished)
        self.player_worker.error.connect(self._on_playback_error)
        self.player_thread.started.connect(self.player_worker.play)
        
        # Start the thread
        self.player_thread.start()
        
        print("PlaybackEngine initialized")

    def _test_direct_playback(self):
        """Test direct playback of a known video file"""
        test_video = "/Users/Matthew/Movies/TV/Media.localized/Stalker.1979.1080p.BluRay.x264.AAC-[YTS.MX].mp4"
        if Path(test_video).exists():
            print(f"Testing direct playback of {test_video}")
            info = SegmentInfo(
                segment=None,
                file_path=test_video,
                start_frame=10000,  # Arbitrary starting point
                end_frame=10300,    # Play 300 frames
                duration=12.5       # Approximate duration
            )
            self.current_segment = info
            self._start_current_segment()
        else:
            print(f"Test video not found: {test_video}")
    
    @Slot()
    def _on_segment_finished(self):
        """Handle segment finishing"""
        print("Segment finished")
        
        # Tell controller we need the next segment
        self.needs_next_segment = True
        self.nextSegmentNeeded.emit()
        
        # If we have a next segment queued, start playing it
        if self.next_segment:
            self._play_next_segment()
    
    @Slot(str)
    def _on_playback_error(self, error_message):
        """Handle playback errors"""
        print(f"Playback error: {error_message}")
        
        # Try to recover by playing next segment if available
        self.needs_next_segment = True
        self.nextSegmentNeeded.emit()
    
    def _play_next_segment(self):
        """Switch to next segment"""
        if not self.next_segment:
            print("No next segment available")
            return
            
        print("Switching to next segment")
        self.current_segment = self.next_segment
        self.next_segment = None
        
        # Stop current playback
        self.player_worker.running = False
        
        # Wait a moment for worker to finish
        QTimer.singleShot(100, self._start_current_segment)
    
    def _start_current_segment(self):
        """Start playing the current segment"""
        if not self.current_segment:
            print("No current segment to play")
            return
            
        print(f"Starting segment playback: {self.current_segment.file_path}")
        print(f"Start frame: {self.current_segment.start_frame}, End frame: {self.current_segment.end_frame}")
        
        # Set the new segment in the worker
        self.player_worker.set_segment(self.current_segment)
        
        # Process events to ensure UI updates
        QCoreApplication.processEvents()
        
        # If thread is not running, start it
        if not self.player_thread.isRunning():
            print("Starting player thread")
            self.player_thread.start()
        else:
            # Otherwise call play directly after a short delay
            print("Thread already running, calling play directly")
            QTimer.singleShot(100, self.player_worker.play)
    
    def queue_segment(self, segment):
        """Queue a segment for playback."""
        # Create SegmentInfo with all necessary data
        info = SegmentInfo(
            segment=segment,
            file_path=str(segment.source_file.path),
            start_frame=segment.start_frame,
            end_frame=segment.end_frame,
            duration=segment.duration
        )
        
        print(f"Queueing segment: {info.file_path}")
        print(f"Frames: {info.start_frame} -> {info.end_frame}")
        
        # Verify file exists
        if not Path(info.file_path).exists():
            print(f"Warning: File does not exist: {info.file_path}")
        
        if self.current_segment is None:
            # This is the first segment, start playing immediately
            self.current_segment = info
            self._start_current_segment()
        else:
            # Store as next segment
            self.next_segment = info
    
    def start(self):
        """Start the playback engine."""
        print("Starting playback engine")
        
        # Make sure the thread is started
        if not self.player_thread.isRunning():
            self.player_thread.start()
        
        # Test direct playback for debugging
        self._test_direct_playback()

        print("Playback engine started")
    
    def stop(self):
        """Stop the playback engine."""
        print("Stopping playback engine")
        
        # Stop the worker
        self.player_worker.running = False
        
        # Stop and wait for thread to finish
        if self.player_thread.isRunning():
            self.player_thread.quit()
            if not self.player_thread.wait(2000):  # Wait up to 2 seconds
                print("Warning: Thread did not terminate properly")
        
        # Reset state
        self.current_segment = None
        self.next_segment = None
        self.needs_next_segment = False
        
        print("Playback engine stopped")
    
    def show(self):
        """Show the display window."""
        print("Showing display window")
        self.display_window.show()