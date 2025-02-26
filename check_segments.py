# check_segments.py
from database.db_manager import DatabaseManager
from database.schema import MediaFile, VideoSegment

def check_database():
    db = DatabaseManager()
    session = db.get_session()
    
    try:
        # Get all media files
        media_files = session.query(MediaFile).all()
        print("\nMedia Files in Database:")
        print("-" * 50)
        for mf in media_files:
            print(f"\nFile: {mf.filename}")
            print(f"Resolution: {mf.width}x{mf.height}")
            print(f"Duration: {mf.duration:.2f} seconds")
            print(f"FPS: {mf.fps}")
            
            # Get segments for this file
            segments = session.query(VideoSegment).filter_by(source_file_id=mf.id).all()
            print(f"Total Segments: {len(segments)}")
            
            # Show first few segments
            print("\nFirst 5 segments:")
            for i, seg in enumerate(segments[:5]):
                print(f"  Segment {i+1}:")
                print(f"    Frames: {seg.start_frame} -> {seg.end_frame}")
                print(f"    Duration: {seg.duration:.2f} seconds")
                print(f"    Scene Score: {seg.scene_score:.2f}")
            
            # Show distribution of segment durations
            durations = [s.duration for s in segments]
            avg_duration = sum(durations) / len(durations) if durations else 0
            print(f"\nAverage segment duration: {avg_duration:.2f} seconds")
            
    finally:
        session.close()

if __name__ == "__main__":
    check_database()