# Placeholder for database manager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .schema import Base

import config

class DatabaseManager:
    def __init__(self):
        self.engine = create_engine(f"sqlite:///{config.DB_PATH}")
        self.Session = sessionmaker(bind=self.engine)
        
    def init_db(self):
        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)
        
    def get_session(self):
        return self.Session()