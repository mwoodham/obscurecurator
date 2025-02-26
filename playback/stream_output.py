# playback/stream_output.py
"""
Streams video output using FFmpeg that can be picked up by VDMX
"""

import os
import subprocess
import threading
import numpy as np
import cv2
import ffmpeg
import tempfile
import time
import queue
from pathlib import Path

class StreamOutput:
    def __init__(self, width=1280, height=720, fps=30, output_url=None):
        """
        Initialize a streaming output that can be consumed by VDMX
        
        Args:
            width (int): Output width
            height (int): Output height
            fps (int): Frames per second
            output_url (str): Optional output URL, defaults to UDP stream
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.output_url = output_url or 'udp://127.0.0.1:23000'
        self.process = None
        self.running = False
        self.frame_queue = queue.Queue(maxsize=30)  # Buffer up to 30 frames
        self.thread = None
        self.temp_dir = Path(tempfile.mkdtemp())
        
        # Create a named pipe for input
        self.pipe_path = self.temp_dir / 'videoinput.pipe'
        if os.name == 'posix':  # macOS, Linux
            if not self.pipe_path.exists():
                os.mkfifo(str(self.pipe_path))
        
        print(f"Stream Output initialized - output: {self.output_url}")
        
    def start(self):
        """Start the streaming process."""
        if self.running:
            return
        
        self.running = True
        
        # Start FFmpeg process
        if os.name == 'posix':  # macOS or Linux - use pipe
            self._start_ffmpeg_pipe()
        else:  # Windows - use memory buffer
            self._start_ffmpeg_memory()
            
        # Start the thread that will feed frames to FFmpeg
        self.thread = threading.Thread(target=self._process_frames)
        self.thread.daemon = True
        self.thread.start()
        
        print(f"Stream started to {self.output_url}")
    
    def _start_ffmpeg_pipe(self):
        """Start FFmpeg using a named pipe for input (macOS/Linux)."""
        command = [
            'ffmpeg',
            '-f', 'rawvideo',
            '-pixel_format', 'bgr24',
            '-video_size', f'{self.width}x{self.height}',
            '-framerate', str(self.fps),
            '-i', str(self.pipe_path),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-f', 'mpegts',
            self.output_url
        ]
        
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Open the pipe for writing
        self.pipe = open(str(self.pipe_path), 'wb')
    
    def _start_ffmpeg_memory(self):
        """Start FFmpeg using memory buffers (Windows)."""
        self.process = (
            ffmpeg
            .input('pipe:', format='rawvideo', pix_fmt='bgr24', 
                  s=f'{self.width}x{self.height}', framerate=self.fps)
            .output(self.output_url, format='mpegts', vcodec='libx264', 
                   preset='ultrafast', tune='zerolatency')
            .global_args('-hide_banner', '-loglevel', 'error')
            .run_async(pipe_stdin=True)
        )
    
    def _process_frames(self):
        """Process frames from the queue and send them to FFmpeg."""
        while self.running:
            try:
                frame = self.frame_queue.get(timeout=1.0)
                
                # Get raw frame bytes
                raw_frame = frame.tobytes()
                
                if os.name == 'posix':  # macOS or Linux
                    # Write to the pipe
                    self.pipe.write(raw_frame)
                    self.pipe.flush()
                else:  # Windows
                    # Write to FFmpeg's stdin
                    self.process.stdin.write(raw_frame)
                    self.process.stdin.flush()
                
                self.frame_queue.task_done()
            except queue.Empty:
                # No frames in queue, just continue
                continue
            except Exception as e:
                print(f"Error processing frame: {e}")
                # Try to recover
                time.sleep(0.1)
    
    def send_frame(self, frame):
        """Send a frame to the stream.
        
        Args:
            frame (numpy.ndarray): BGR frame to send
        """
        if not self.running:
            return False
        
        # Resize frame if needed
        if frame.shape[0] != self.height or frame.shape[1] != self.width:
            frame = cv2.resize(frame, (self.width, self.height))
        
        # Add frame to queue, non-blocking (drop frames if queue is full)
        try:
            self.frame_queue.put_nowait(frame)
            return True
        except queue.Full:
            # Queue is full, drop this frame
            print("Warning: Frame dropped, queue full")
            return False
    
    def stop(self):
        """Stop the streaming process."""
        if not self.running:
            return
        
        self.running = False
        
        # Wait for thread to finish
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        
        # Close pipe if open
        if os.name == 'posix' and hasattr(self, 'pipe'):
            self.pipe.close()
        
        # Terminate FFmpeg process
        if self.process:
            if hasattr(self.process, 'stdin'):
                self.process.stdin.close()
            if hasattr(self.process, 'terminate'):
                self.process.terminate()
            else:
                self.process.kill()  # ffmpeg-python style
        
        print("Stream stopped")
    
    def cleanup(self):
        """Clean up resources."""
        self.stop()
        
        # Remove temporary directory
        if self.temp_dir.exists():
            for file in self.temp_dir.iterdir():
                if file.is_file():
                    file.unlink()
            self.temp_dir.rmdir()
        
        print("Stream resources cleaned up")


# Example usage:
if __name__ == "__main__":
    # This is a simple test to verify the streaming works
    streamer = StreamOutput(width=1280, height=720)
    streamer.start()
    
    # Create a test video source (a moving rectangle)
    cap = cv2.VideoCapture(0)  # Use webcam for testing
    
    if not cap.isOpened():
        # No webcam, create synthetic frames
        for i in range(100):
            # Create a blank frame
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            
            # Draw a moving rectangle
            x = int(i * 10) % 1200
            cv2.rectangle(frame, (x, 300), (x + 80, 400), (0, 255, 0), -1)
            
            # Add some text
            cv2.putText(frame, f"Frame {i}", (50, 50), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            # Send the frame
            streamer.send_frame(frame)
            
            # Wait a bit
            time.sleep(1/30)
    else:
        # Use webcam frames
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Resize if needed
                frame = cv2.resize(frame, (1280, 720))
                
                # Send the frame
                streamer.send_frame(frame)
                
                # Display the frame locally
                cv2.imshow('Stream Test', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        finally:
            cap.release()
            cv2.destroyAllWindows()
    
    # Clean up
    streamer.cleanup()