from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite:///submissions.db"

# Create Database Engine
# check_same_thread=False is required for SQLite in multithreaded FastAPI apps
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False}
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative Base
Base = declarative_base()

class SalarySubmissionDB(Base):
    """SQLAlchemy model representing the salary submissions table."""
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    company = Column(String, index=True, nullable=False)
    role = Column(String, index=True, nullable=False)
    location = Column(String, index=True, nullable=False)
    yearsOfExperience = Column(Float, nullable=False)
    offerDate = Column(String, nullable=True)
    year = Column(Integer, nullable=False)
    totalCompensation = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    totalCompensationINR = Column(Float, nullable=False)
    level = Column(String, index=True, nullable=True)
    baseSalaryINR = Column(Float, nullable=True)
    stockINR = Column(Float, nullable=True)
    bonusINR = Column(Float, nullable=True)
    ipAddress = Column(String, index=True, nullable=False)
    trust_score = Column(Float, nullable=False)
    status = Column(String, nullable=False)  # accepted or flagged
    reasons = Column(JSON, nullable=False)   # List of reasons stored as JSON
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    """Initializes schema in the SQLite database file, dropping existing tables if schema is updated."""
    from sqlalchemy import inspect
    inspector = inspect(engine)
    if "submissions" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("submissions")]
        if "level" not in columns:
            print("Database schema mismatch detected. Recreating submissions database...")
            Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def get_db():
    """Generates database sessions for routes (dependency injection)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
