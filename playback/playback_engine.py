import cv2
import queue
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from collections import OrderedDict
from PySide6.QtWidgets import QMainWindow
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QImage
from sqlalchemy.orm import joinedload

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

class DisplayWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Media Collage Output")
        self.setFixedSize(1280, 720)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        
        # Initialize frame buffer
        self.current_frame = None
        
        print("Display window initialized")
    
    def updateFrame(self, frame):
        """Update the current frame"""
        if frame is not None:
            # Process frame
            frame = cv2.resize(frame, (1280, 720))
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.current_frame = rgb_frame
            self.update()
    
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

class PlaybackEngine:
    def __init__(self, db_manager, max_videos=5):
        self.db_manager = db_manager
        self.max_videos = max_videos
        self.video_buffers: Dict[str, VideoBuffer] = OrderedDict()
        self.frame_queue = queue.Queue(maxsize=60)  # 2 seconds at 30fps
        self.current_segment: Optional[SegmentInfo] = None
        self.next_segment: Optional[SegmentInfo] = None
        self.needs_next_segment = False
        self.playback_thread = None
        self.buffer_thread = None
        self.running = False
        self.target_fps = 24  # Default FPS, will be updated per video
        
        # Create display window
        self.display_window = DisplayWindow()
        
        # Setup display timer - will be configured per video
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_display)
        
        print("PlaybackEngine initialized")
    
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
        
        # Update FPS if needed
        cap = cv2.VideoCapture(info.file_path)
        if cap.isOpened():
            self.target_fps = cap.get(cv2.CAP_PROP_FPS)
            # Update timer interval
            interval = int(1000 / self.target_fps)  # Convert FPS to milliseconds
            self.timer.start(interval)
            print(f"Set playback speed to {self.target_fps} FPS")
            cap.release()
        
        if self.current_segment is None:
            self.current_segment = info
        else:
            self.next_segment = info
    
    def _get_video_capture(self, file_path: str) -> Optional[cv2.VideoCapture]:
        """Get or create a VideoCapture object for the file."""
        if file_path in self.video_buffers:
            buf = self.video_buffers[file_path]
            buf.last_access = time.time()
            buf.ref_count += 1
            return buf.cap
        
        # Make room if needed
        while len(self.video_buffers) >= self.max_videos:
            for old_path, buf in list(self.video_buffers.items()):
                if buf.ref_count == 0:
                    buf.cap.release()
                    del self.video_buffers[old_path]
                    break
        
        # Create new VideoCapture
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            print(f"Could not open video: {file_path}")
            return None
        
        self.video_buffers[file_path] = VideoBuffer(
            cap=cap,
            last_access=time.time(),
            ref_count=1
        )
        
        return cap
    
    def _release_video(self, file_path: str):
        """Release a video when no longer needed."""
        if file_path in self.video_buffers:
            buf = self.video_buffers[file_path]
            buf.ref_count -= 1
            if buf.ref_count <= 0:
                buf.ref_count = 0
    
    def _buffer_loop(self):
        """Background thread to keep frame buffer filled."""
        while self.running:
            try:
                if self.current_segment and self.frame_queue.qsize() < 30:
                    cap = self._get_video_capture(self.current_segment.file_path)
                    if not cap:
                        continue
                    
                    current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                    if current_frame < self.current_segment.start_frame or \
                       current_frame >= self.current_segment.end_frame:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_segment.start_frame)
                    
                    ret, frame = cap.read()
                    if ret and current_frame < self.current_segment.end_frame:
                        try:
                            self.frame_queue.put(frame, timeout=1)
                            if current_frame % 30 == 0:
                                print(f"Buffered frame {current_frame}")
                        except queue.Full:
                            pass
                    
                    self._release_video(self.current_segment.file_path)
                else:
                    time.sleep(0.01)
                    
            except Exception as e:
                print(f"Error in buffer loop: {e}")
                time.sleep(0.1)
    
    def _update_display(self):
        """Update display with next frame"""
        try:
            if not self.frame_queue.empty():
                frame = self.frame_queue.get_nowait()
                self.display_window.updateFrame(frame)
        except Exception as e:
            print(f"Error updating display: {e}")
    
    def _playback_loop(self):
        """Main playback loop."""
        while self.running:
            try:
                if self.current_segment:
                    cap = self._get_video_capture(self.current_segment.file_path)
                    if cap:
                        current_frame = cap.get(cv2.CAP_PROP_POS_FRAMES)
                        if current_frame >= self.current_segment.end_frame:
                            print("\nReached end of segment")
                            if self.next_segment:
                                print("Switching to next segment")
                                self.current_segment = self.next_segment
                                self.next_segment = None
                            else:
                                print("Requesting next segment")
                                self.needs_next_segment = True
                            
                        self._release_video(self.current_segment.file_path)
                
                time.sleep(0.01)
                
            except Exception as e:
                print(f"Error in playback loop: {e}")
                time.sleep(0.1)
    
    def start(self):
        """Start the playback engine."""
        if self.running:
            return
        
        print("Starting playback engine")
        self.running = True
        
        # Start threads
        self.playback_thread = threading.Thread(target=self._playback_loop)
        self.playback_thread.daemon = True
        self.playback_thread.start()
        
        self.buffer_thread = threading.Thread(target=self._buffer_loop)
        self.buffer_thread.daemon = True
        self.buffer_thread.start()
        
        print("Playback engine started")
    
    def stop(self):
        """Stop the playback engine."""
        self.running = False
        if self.playback_thread:
            self.playback_thread.join()
        if self.buffer_thread:
            self.buffer_thread.join()
        for buf in self.video_buffers.values():
            buf.cap.release()
        self.video_buffers.clear()
    
    def show(self):
        """Show the display window."""
        self.display_window.show()