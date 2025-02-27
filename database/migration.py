import os
import sys
import argparse
from pathlib import Path
import logging
import datetime
import enum
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey, Text, LargeBinary, DateTime, Enum, MetaData, Table, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(config.DATA_DIR, "migration.log")),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("database_migration")

# Import the new schema definitions
from database.schema import Base, ProcessingStatus, MediaFile, VideoSegment, SegmentFeature, Tag, ProcessingCheckpoint

def backup_database():
    """Create a backup of the current database file."""
    db_path = Path(config.DB_PATH)
    if db_path.exists():
        backup_path = db_path.with_suffix(f".backup-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.db")
        import shutil
        shutil.copy2(db_path, backup_path)
        logger.info(f"Created database backup: {backup_path}")
        return backup_path
    return None

def create_engine_session():
    """Create SQLAlchemy engine and session."""
    engine = create_engine(f"sqlite:///{config.DB_PATH}")
    Session = sessionmaker(bind=engine)
    return engine, Session

def check_tables_exist(engine):
    """Check if the required tables exist in the database."""
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    required_tables = ['media_files', 'video_segments', 'segment_features', 'tags']
    
    return all(table in existing_tables for table in required_tables)

def migrate_database():
    """Perform database migration to the new schema."""
    logger.info("Starting database migration")
    
    # Create a backup first
    backup_path = backup_database()
    if backup_path:
        logger.info(f"Database backup created at {backup_path}")
    
    # Create engine and session
    engine, Session = create_engine_session()
    
    # Check if tables exist
    tables_exist = check_tables_exist(engine)
    
    if not tables_exist:
        logger.info("This appears to be a fresh install. Creating tables.")
        Base.metadata.create_all(engine)
        logger.info("Database tables created successfully.")
        return True
    
    # Check if we need to migrate
    inspector = inspect(engine)
    media_file_columns = [column['name'] for column in inspector.get_columns('media_files')]
    
    # If processing_status is already present, we've already migrated
    if 'processing_status' in media_file_columns:
        logger.info("Database schema is already up to date.")
        return True
    
    try:
        logger.info("Starting schema migration...")
        
        # Get metadata from existing tables
        metadata = MetaData()
        metadata.reflect(bind=engine)
        
        # Create a session
        session = Session()
        
        # Step 1: Add new columns to media_files table using ALTER TABLE
        conn = engine.connect()
        
        # Add new columns to media_files
        try:
            logger.info("Adding new columns to media_files table...")
            for column_name, column_type in [
                ('processing_status', 'TEXT'),
                ('scene_detection_complete', 'BOOLEAN'),
                ('features_extraction_complete', 'BOOLEAN'),
                ('created_at', 'TIMESTAMP'),
                ('updated_at', 'TIMESTAMP'),
                ('processing_started_at', 'TIMESTAMP'),
                ('processing_completed_at', 'TIMESTAMP'),
                ('scene_detection_progress', 'FLOAT'),
                ('feature_extraction_progress', 'FLOAT'),
                ('last_error', 'TEXT'),
                ('error_count', 'INTEGER')
            ]:
                try:
                    conn.execute(f"ALTER TABLE media_files ADD COLUMN {column_name} {column_type}")
                except Exception as e:
                    logger.warning(f"Could not add column {column_name}: {e}")
        except Exception as e:
            logger.error(f"Error adding columns to media_files: {e}")
            raise
        
        # Add new columns to video_segments
        try:
            logger.info("Adding new columns to video_segments table...")
            for column_name, column_type in [
                ('processing_status', 'TEXT'),
                ('features_extracted', 'BOOLEAN'),
                ('created_at', 'TIMESTAMP'),
                ('updated_at', 'TIMESTAMP'),
                ('processing_started_at', 'TIMESTAMP'),
                ('processing_completed_at', 'TIMESTAMP'),
                ('last_error', 'TEXT'),
                ('error_count', 'INTEGER')
            ]:
                try:
                    conn.execute(f"ALTER TABLE video_segments ADD COLUMN {column_name} {column_type}")
                except Exception as e:
                    logger.warning(f"Could not add column {column_name}: {e}")
        except Exception as e:
            logger.error(f"Error adding columns to video_segments: {e}")
            raise
        
        # Add timestamps to segment_features
        try:
            logger.info("Adding timestamps to segment_features table...")
            for column_name, column_type in [
                ('created_at', 'TIMESTAMP'),
                ('updated_at', 'TIMESTAMP')
            ]:
                try:
                    conn.execute(f"ALTER TABLE segment_features ADD COLUMN {column_name} {column_type}")
                except Exception as e:
                    logger.warning(f"Could not add column {column_name}: {e}")
        except Exception as e:
            logger.error(f"Error adding columns to segment_features: {e}")
            raise
        
        # Add timestamps to tags
        try:
            logger.info("Adding timestamp to tags table...")
            try:
                conn.execute("ALTER TABLE tags ADD COLUMN created_at TIMESTAMP")
            except Exception as e:
                logger.warning(f"Could not add created_at to tags: {e}")
        except Exception as e:
            logger.error(f"Error adding column to tags: {e}")
            raise
        
        # Create new processing_checkpoints table
        try:
            logger.info("Creating processing_checkpoints table...")
            ProcessingCheckpoint.__table__.create(engine)
        except Exception as e:
            logger.error(f"Error creating processing_checkpoints table: {e}")
            raise
        
        # Step 2: Migrate data to new schema columns
        try:
            logger.info("Migrating existing data to new schema...")
            
            # Update media_files
            media_files = session.execute("SELECT id, processed FROM media_files").fetchall()
            now = datetime.datetime.utcnow()
            
            for file_id, processed in media_files:
                status = ProcessingStatus.COMPLETED.value if processed else ProcessingStatus.PENDING.value
                session.execute(
                    "UPDATE media_files SET "
                    "processing_status = :status, "
                    "scene_detection_complete = :processed, "
                    "features_extraction_complete = :processed, "
                    "created_at = :now, "
                    "updated_at = :now, "
                    "scene_detection_progress = :progress, "
                    "feature_extraction_progress = :progress, "
                    "error_count = 0 "
                    "WHERE id = :id",
                    {
                        "status": status,
                        "processed": processed,
                        "now": now,
                        "progress": 100.0 if processed else 0.0,
                        "id": file_id
                    }
                )
            
            # Update video_segments
            segments = session.execute("SELECT id, processed FROM video_segments").fetchall()
            
            for segment_id, processed in segments:
                status = ProcessingStatus.COMPLETED.value if processed else ProcessingStatus.PENDING.value
                session.execute(
                    "UPDATE video_segments SET "
                    "processing_status = :status, "
                    "features_extracted = :processed, "
                    "created_at = :now, "
                    "updated_at = :now, "
                    "error_count = 0 "
                    "WHERE id = :id",
                    {
                        "status": status,
                        "processed": processed,
                        "now": now,
                        "id": segment_id
                    }
                )
            
            session.commit()
            logger.info("Data migration completed successfully.")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error migrating data: {e}")
            raise
        
        logger.info("Database migration completed successfully.")
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        logger.info(f"Restoring from backup {backup_path}")
        
        # Restore from backup if something went wrong
        if backup_path:
            try:
                import shutil
                db_path = Path(config.DB_PATH)
                shutil.copy2(backup_path, db_path)
                logger.info("Database restored from backup.")
            except Exception as restore_error:
                logger.error(f"Error restoring backup: {restore_error}")
        
        return False

def main():
    parser = argparse.ArgumentParser(description="Database Migration Tool")
    parser.add_argument("--force", action="store_true", help="Force migration even if tables exist")
    parser.add_argument("--backup-only", action="store_true", help="Only create a backup, don't migrate")
    args = parser.parse_args()
    
    # Check if database file exists
    db_path = Path(config.DB_PATH)
    if not db_path.parent.exists():
        logger.info(f"Creating directory {db_path.parent}")
        db_path.parent.mkdir(parents=True, exist_ok=True)
    
    if args.backup_only:
        backup_path = backup_database()
        if backup_path:
            logger.info(f"Database backup created at {backup_path}")
        else:
            logger.warning("No database file to backup.")
        return
    
    # Perform migration
    success = migrate_database()
    
    if success:
        logger.info("Migration completed successfully.")
    else:
        logger.error("Migration failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()