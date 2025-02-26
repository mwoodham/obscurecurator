# test_window.py
import sys
import cv2
import numpy as np
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QImage

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Display Test")
        self.setFixedSize(1280, 720)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        
        # Create test pattern
        self.frame_count = 0
        
        # Setup timer for animation
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(33)  # ~30fps
        
        print("Test window initialized")
    
    def update_frame(self):
        self.frame_count += 1
        self.update()
        
    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            
            # Create animated test pattern
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            
            # Draw moving circle
            cx = int(640 + 300 * np.cos(self.frame_count * 0.05))
            cy = int(360 + 200 * np.sin(self.frame_count * 0.05))
            cv2.circle(frame, (cx, cy), 50, (0, 255, 0), -1)
            
            # Add frame counter
            cv2.putText(frame, f"Frame {self.frame_count}", 
                       (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 
                       1, (255, 255, 255), 2)
            
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Create QImage
            image = QImage(rgb_frame.data, 1280, 720, 1280 * 3, QImage.Format_RGB888)
            
            # Draw to window
            painter.drawImage(0, 0, image)
            print(f"Drew frame {self.frame_count}")
            
        except Exception as e:
            print(f"Error in paint event: {e}")
            painter.fillRect(self.rect(), Qt.black)

def main():
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    return app.exec()

if __name__ == "__main__":
    main()