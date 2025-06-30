from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models import Base

DATABASE_URL = "sqlite:///data/stig.db"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)