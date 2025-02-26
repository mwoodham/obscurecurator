# simple_player.py
import sys
import cv2
import time
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QImage
from database.db_manager import DatabaseManager
from database.schema import VideoSegment, MediaFile
from sqlalchemy.orm import joinedload

class VideoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Media Collage")
        self.setFixedSize(1280, 720)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        
        # Video playback state
        self.cap = None
        self.current_segment = None
        self.current_frame = None
        self.db = DatabaseManager()
        self.segments = []
        self.segment_index = -1
        
        # Setup display timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(33)  # ~30fps
        
        print("Video window initialized")
    
    def load_segments(self):
        """Load all segments from database"""
        session = self.db.get_session()
        try:
            # Use joinedload to eagerly load the source_file relationship
            self.segments = session.query(VideoSegment)\
                .options(joinedload(VideoSegment.source_file))\
                .all()
            print(f"Loaded {len(self.segments)} segments")
            
            # Store file paths to avoid database access during playback
            self.segments = [(segment, str(segment.source_file.path)) 
                           for segment in self.segments]
        finally:
            session.close()
    
    def next_segment(self):
        """Switch to next segment"""
        if not self.segments:
            return
            
        # Move to next segment
        self.segment_index = (self.segment_index + 1) % len(self.segments)
        self.current_segment, file_path = self.segments[self.segment_index]
        
        print(f"\nPlaying segment {self.segment_index + 1}/{len(self.segments)}")
        print(f"File: {file_path}")
        print(f"Frames: {self.current_segment.start_frame} -> {self.current_segment.end_frame}")
        
        # Open video if needed
        if self.cap is not None:
            self.cap.release()
            
        self.cap = cv2.VideoCapture(file_path)
        if not self.cap.isOpened():
            print(f"Failed to open video file: {file_path}")
            return
            
        # Seek to segment start
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_segment.start_frame)
    
    def update_frame(self):
        """Read and display next frame"""
        try:
            if self.cap is None or self.current_segment is None:
                self.next_segment()
                return
                
            # Check if we need to switch segments
            current_frame_pos = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
            if current_frame_pos >= self.current_segment.end_frame:
                self.next_segment()
                return
                
            # Read frame
            ret, frame = self.cap.read()
            if not ret:
                print("Failed to read frame")
                self.next_segment()
                return
                
            # Process frame
            frame = cv2.resize(frame, (1280, 720))
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Store for display
            self.current_frame = rgb_frame
            
            # Request paint
            self.update()
            print(f"Frame {current_frame_pos} displayed")
            
        except Exception as e:
            print(f"Error updating frame: {e}")
    
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
            print(f"Error painting: {e}")
            painter.fillRect(self.rect(), Qt.black)

def main():
    app = QApplication(sys.argv)
    window = VideoWindow()
    window.load_segments()
    window.show()
    return app.exec()

if __name__ == "__main__":
    main()