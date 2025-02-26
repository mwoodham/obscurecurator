import cv2
import numpy as np
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QImage

class DisplayWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Media Collage Output")
        
        # Set fixed size window
        self.setFixedSize(1280, 720)
        
        # Create central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Remove window frame for clean capture
        self.setWindowFlags(Qt.FramelessWindowHint)
        
        # Animation variables
        self.frame_count = 0
        self.start_time = 0
        
        # Setup animation timer (60 FPS)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(1000 // 60)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        
        # Create test pattern
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        
        # Animated pattern
        t = self.frame_count * 0.02
        cx = int(640 + 300 * np.cos(t))
        cy = int(360 + 200 * np.sin(t))
        
        # Draw gradient background
        for y in range(720):
            color = int(255 * y / 720)
            frame[y, :] = [color, 0, color]
        
        # Draw moving circle
        cv2.circle(frame, (cx, cy), 50, (0, 255, 0), -1)
        
        # Add frame counter
        cv2.putText(frame, 
                   f"Frame {self.frame_count}", 
                   (50, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 
                   1, 
                   (255, 255, 255), 
                   2)
        
        # Convert to Qt image
        h, w = frame.shape[:2]
        image = QImage(frame.data, w, h, 3 * w, QImage.Format_RGB888)
        
        # Draw the image
        painter.drawImage(0, 0, image)
        
        self.frame_count += 1

def main():
    app = QApplication([])
    
    window = DisplayWindow()
    window.show()
    
    print("\nTest window created!")
    print("1. In VDMX, add a new 'Windows in Applications' layer")
    print("2. Select 'Media Collage Output' from the window list")
    print("3. You should see the animated pattern")
    print("\nPress Ctrl+C in this terminal to exit")
    
    app.exec()

if __name__ == "__main__":
    main()