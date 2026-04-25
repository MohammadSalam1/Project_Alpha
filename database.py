from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime

# SQLite database stored in the project folder.
# This keeps the project simple for local development and testing.
DATABASE_URL = "sqlite:///./alpha.db"

# SQLAlchemy engine configured for SQLite.
# check_same_thread=False is required so FastAPI can use the DB across threads.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# Session factory used to create short-lived database sessions per request.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all ORM models in this project.
Base = declarative_base()

class Device(Base):
    # Table that stores the monitored devices.
    __tablename__ = "devices"

    # Primary key for each device row.
    id = Column(Integer, primary_key=True, index=True)

    # Human-readable name shown in the dashboard.
    name = Column(String, nullable=False)

    # IP address or host to monitor.
    # Unique prevents accidentally adding the same address twice.
    ip_address = Column(String, nullable=False, unique=True)

    # Allows disabling a device without deleting it.
    enabled = Column(Boolean, default=True)

    # Relationship to the history table.
    # A device can have many ping results over time.
    checks = relationship("Check", back_populates="device")

class Check(Base):
    # Table that stores each ping result over time.
    __tablename__ = "checks"

    # Primary key for each check row.
    id = Column(Integer, primary_key=True, index=True)

    # Foreign key linking a check back to a monitored device.
    device_id = Column(Integer, ForeignKey("devices.id"))

    # Whether the device was reachable during this check.
    is_up = Column(Boolean, default=False)

    # Timestamp for when the check was recorded.
    checked_at = Column(DateTime, default=datetime.utcnow)

    # Back-reference to the parent device.
    device = relationship("Device", back_populates="checks")

# Create tables automatically when the app starts.
# This is convenient for a small local project.
Base.metadata.create_all(bind=engine)

def get_db():
    # Dependency that opens a database session for one request.
    # The session is always closed after the request finishes.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()