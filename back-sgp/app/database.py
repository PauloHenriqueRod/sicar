from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.security import configured_database_url

load_dotenv()
SQLALCHEMY_DATABASE_URL = configured_database_url()

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}, hide_parameters=True
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL, hide_parameters=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
