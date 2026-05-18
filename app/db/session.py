# app/db/session.py
# ════════════════════════════════════════════════
# Database Session Management
#
# WHY THIS FILE EXISTS:
# Creates and manages connections to PostgreSQL.
# Every database operation needs a session.
# Think of it like opening and closing a
# connection to the database for each request.
#
# HOW IT WORKS:
# 1. App starts → engine connects to Supabase
# 2. Request comes in → get_db() opens a session
# 3. Route does DB operations using that session
# 4. Request ends → session commits and closes
# 5. If error → session rolls back all changes
#
#-------------IMPORTANT----------------------
# Never create engine or SessionLocal yourself.
# Always import get_db and use it as a
# FastAPI dependency in your routes.
# ════════════════════════════════════════════════

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger(__name__)

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True, # tests connection before using it
    pool_size=10, #keps 10 connections open and ready
    max_overflow=20, # 20 extra connections allowed on heavy load
    echo=settings.DEBUG
) # engine is the core connection for Postgre_SQL 
SessionLocal = sessionmaker(
    autocommit=False,# manual control over commit
    autoflush=False,# we control when SQLalchemy sync
    bind=engine
)# creates local database session

#dependency-----
def get_db():
    """ 
    FastAPI dependency that provides a DB session.

    How to use in any route:
        from sqlalchemy.orm import Session
        from fastapi import Depends
        from app.db.session import get_db

        @router.get("/assignments")
        def list_assignments(db: Session = Depends(get_db)):
            return db.query(Assignment).all()
    """
    
    db = SessionLocal() #opens the fresh session
    try:
        log.debug("Db_session_opened")
        yield db
        db.commit()
        log.debug("Db_session_commited")
    except Exception as e:
        log.error("db_session_rolllback",
        error = str(e),
        exc_info= True )
        db.rollback()
        raise
    finally:
        db.close()
        log.debug("db_session_closed")
        #Why use yield instead of return?
        #yield pauses the function and gives control
        #to the route. When route finishes, execution
        #returns here and the finally block runs.
# DB helth check

def check_db_connection() -> bool:
    """
    Tests if database is reachable.
    Returns:
        True if connected successfully
        False if connection failed
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        log.info("db_connection_ok",
                 host=settings.DATABASE_URL.split("@")[-1][:30])
        return True
    except Exception as e:
        log.error("db_connection_failed",
                  error=str(e),
                  exc_info=True)
        return False


# ── Create All Tables ─────────────────────────────
def create_tables():
    """
    Creates all tables defined in models.py.
    Only used in development or testing.

    Why not use this in production?
        This creates tables but cannot handle changes
        to existing tables. Alembic can add columns,
        rename tables, and migrate data safely.
    """
    from app.db.models import Base
    Base.metadata.create_all(bind=engine)
    log.info("db_tables_created")
        
        

