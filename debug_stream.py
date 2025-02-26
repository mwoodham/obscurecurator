import cv2
import numpy as np
import time
import subprocess

class StreamOutput:
    def __init__(self, width=1280, height=720, fps=30):
        self.width = width
        self.height = height
        self.fps = fps
        self.process = None
        self.running = False
        
    def start(self):
        """Start the streaming process with optimized parameters for smooth playback."""
        command = [
            'ffmpeg',
            '-y',  # Overwrite output
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-pixel_format', 'bgr24',
            '-video_size', f'{self.width}x{self.height}',
            '-framerate', str(self.fps),
            '-i', '-',  # Read from pipe
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-x264-params', 'keyint=30:min-keyint=30',  # Keyframe settings
            '-b:v', '5000k',  # Higher bitrate for better quality
            '-bufsize', '5000k',
            '-maxrate', '5000k',
            '-pix_fmt', 'yuv420p',
            '-f', 'mpegts',
            '-flush_packets', '1',
            '-thread_queue_size', '512',
            'udp://127.0.0.1:23000?pkt_size=1316&buffer_size=65535'
        ]
        
        print("Starting FFmpeg with command:", ' '.join(command))
        
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0  # Unbuffered
        )
        self.running = True

    def send_frame(self, frame):
        if not self.running or not self.process:
            return False
        try:
            self.process.stdin.write(frame.tobytes())
            return True
        except Exception as e:
            print(f"Error sending frame: {e}")
            return False
    
    def stop(self):
        self.running = False
        if self.process:
            try:
                if self.process.stdin:
                    self.process.stdin.close()
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception as e:
                print(f"Error stopping process: {e}")
                try:
                    self.process.kill()
                except:
                    pass
        self.process = None

def test_stream():
    """Test the UDP stream with smooth animation pattern."""
    print("\n=== Starting UDP Stream Test ===")
    print("You can view this stream in:")
    print("1. VLC: udp://@127.0.0.1:23000")
    print("2. VDMX: Add UDP Stream Layer, port 23000")
    print("\nStarting in 10 seconds...")
    
    for i in range(10, 0, -1):
        print(f"{i}...", end='\r', flush=True)
        time.sleep(1)
    print("\n")
    
    streamer = StreamOutput(width=1280, height=720, fps=30)
    last_frame_time = time.time()
    frame_interval = 1.0 / 30.0  # Target 30 FPS
    
    try:
        print("Starting stream...")
        streamer.start()
        print("Stream started!")
        
        print("\nCreating test pattern...")
        for i in range(300):  # 5 minutes
            current_time = time.time()
            elapsed = current_time - last_frame_time
            
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)
            
            # Create test pattern
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            
            # Smooth animated pattern
            t = i * 0.05  # Slower movement
            cx = int(640 + 300 * np.cos(t))
            cy = int(360 + 200 * np.sin(t))
            
            # Gradient background
            for y in range(720):
                color = int(255 * y / 720)
                frame[y, :] = [color, 0, color]
            
            # Smooth moving circle
            cv2.circle(frame, (cx, cy), 50, (0, 255, 0), -1)
            
            # Frame border
            cv2.rectangle(frame, (50, 50), (1230, 670), (255, 0, 0), 2)
            
            # Frame counter and timestamp
            cv2.putText(frame, 
                       f"Frame {i} - {time.strftime('%H:%M:%S')}", 
                       (100, 100),
                       cv2.FONT_HERSHEY_SIMPLEX, 
                       1.5,
                       (255, 255, 255),
                       2)
            
            success = streamer.send_frame(frame)
            
            # Display locally
            cv2.imshow('Local Preview', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            
            last_frame_time = time.time()
            
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"\nError during streaming: {e}")
    finally:
        print("\nCleaning up...")
        streamer.stop()
        cv2.destroyAllWindows()
    
    print("\n=== Stream Test Complete ===")
    print("\nViewing options:")
    print("\nVLC:")
    print("1. Media -> Open Network Stream")
    print("2. Enter: udp://@127.0.0.1:23000")
    print("3. Show advanced options")
    print("4. Set Caching to 50ms")
    print("5. Set Network caching to 50ms")
    print("\nVDMX:")
    print("1. Add new UDP Stream Layer")
    print("2. Set port to 23000")
    print("3. If needed, adjust buffer settings in VDMX preferences")

if __name__ == "__main__":
    test_stream()