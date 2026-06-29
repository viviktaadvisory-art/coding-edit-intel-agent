import datetime
from sqlalchemy.orm import Session
from app.db.init_db import ObservabilityLog

class LogService:
    @staticmethod
    def add_log(db: Session, message: str, log_type: str = "INFO") -> ObservabilityLog:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_entry = ObservabilityLog(
            timestamp=timestamp,
            type=log_type.upper(),
            message=message
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry

    @staticmethod
    def get_logs(db: Session, limit: int = 100) -> list:
        # Query logs from SQLite DB (Newest last, reversing order)
        logs = db.query(ObservabilityLog).order_by(ObservabilityLog.id.desc()).limit(limit).all()
        return logs[::-1]
