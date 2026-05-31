import os
import logging
from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
logger = logging.getLogger(__name__)

DB_USER = os.getenv("POSTGRES_USER")
DB_PASS = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("POSTGRES_HOST")
DB_PORT = os.getenv("POSTGRES_PORT")
DB_NAME = os.getenv("POSTGRES_DB")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

Base = declarative_base()

class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    phone = Column(String)
    address = Column(Text)
    expected_salary = Column(Float)
    job_profile = Column(String)
    role = Column(String)
    status = Column(String, default="Pending") # Pending, Interviewing, Selected, Rejected

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_db_engine():
    """Self-healing DB connection."""
    try:
        engine = create_engine(DATABASE_URL)
        Base.metadata.create_all(bind=engine)
        return engine
    except Exception as e:
        logger.error(f"Database connection failed, retrying... {str(e)}")
        raise e

engine = get_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def update_candidate_status(candidate_name: str, new_status: str, data: dict = None):
    """Used by agents to update ATS state."""
    db = SessionLocal()
    try:
        candidate = db.query(Candidate).filter(Candidate.name == candidate_name).first()
        if not candidate:
            candidate = Candidate(name=candidate_name, **(data or {}))
            db.add(candidate)
        candidate.status = new_status
        db.commit()
        return f"Success: {candidate_name} marked as {new_status}."
    finally:
        db.close()