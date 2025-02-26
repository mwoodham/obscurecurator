# test_continuous.py
import sys
import cv2
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from database.db_manager import DatabaseManager
from database.schema import VideoSegment
from playback.playback_engine import PlaybackEngine

class ContinuousPlayer:
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.session = self.db_manager.get_session()
        self.playback = PlaybackEngine(self.db_manager)
        self.segments = []
        self.current_index = -1
        
        # Load all segments at start
        self.segments = self.session.query(VideoSegment).all()
        print(f"Loaded {len(self.segments)} segments")
        
        # Setup timers
        self.segment_timer = QTimer()
        self.segment_timer.timeout.connect(self.check_segments)
        self.segment_timer.start(100)  # Check every 100ms
        
        # Setup display timer
        self.display_timer = QTimer()
        self.display_timer.timeout.connect(self.update_display)
        self.display_timer.start(33)  # ~30fps
    
    def get_next_segment(self):
        """Get the next segment from the database"""
        if not self.segments:
            return None
            
        self.current_index = (self.current_index + 1) % len(self.segments)
        return self.segments[self.current_index]
    
    def check_segments(self):
        """Check if we need to queue a new segment"""
        if self.playback.needs_next_segment:
            print("\nNeed next segment")
            next_segment = self.get_next_segment()
            if next_segment:
                print(f"\nQueuing segment {self.current_index + 1}/{len(self.segments)}")
                print(f"File: {next_segment.source_file.filename}")
                print(f"Frames: {next_segment.start_frame} -> {next_segment.end_frame}")
                print(f"Duration: {next_segment.duration:.2f} seconds")
                self.playback.queue_segment(next_segment)
            else:
                print("No more segments available")
                # Loop back to start
                self.current_index = -1
                next_segment = self.get_next_segment()
                if next_segment:
                    print("Looping back to first segment")
                    self.playback.queue_segment(next_segment)
    
    def update_display(self):
        """Update the display"""
        self.playback._update_display()
    
    def run(self):
        # Queue initial segment
        next_segment = self.get_next_segment()
        if next_segment:
            print(f"\nQueuing initial segment")
            print(f"File: {next_segment.source_file.filename}")
            print(f"Frames: {next_segment.start_frame} -> {next_segment.end_frame}")
            print(f"Duration: {next_segment.duration:.2f} seconds")
            self.playback.queue_segment(next_segment)
        
        # Start playback
        print("\nStarting playback")
        # Position window in top-left corner
        self.playback.display_window.move(0, 0)
        self.playback.show()
        self.playback.start()

def main():
    app = QApplication(sys.argv)
    player = ContinuousPlayer()
    player.run()
    return app.exec()

if __name__ == "__main__":
    main()