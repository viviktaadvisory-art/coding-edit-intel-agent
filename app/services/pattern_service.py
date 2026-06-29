from sqlalchemy.orm import Session
from app.db.init_db import ProviderProfile

class PatternService:
    @staticmethod
    def audit_provider_profile(db: Session, npi: str) -> dict:
        profile = db.query(ProviderProfile).filter(ProviderProfile.npi == npi).first()
        if profile:
            return {
                "name": profile.provider_name,
                "level5_freq": profile.level5_freq,
                "mod25_freq": profile.mod25_freq,
                "risk_level": profile.risk_level,
                "reasons": profile.reasons
            }
        return {
            "name": "Unknown Provider",
            "level5_freq": 0,
            "mod25_freq": 0,
            "risk_level": "LOW",
            "reasons": "New provider. No billing history logs available."
        }
