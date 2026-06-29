import re
import hashlib
from sqlalchemy.orm import Session
from app.db.init_db import IAMMapping

class IAMService:
    @staticmethod
    def get_pseudo_and_case_id(patient_name: str, claim_id: str) -> tuple:
        # Create reproducible non-attributable hashes
        name_hash = hashlib.md5(patient_name.strip().lower().encode()).hexdigest()
        claim_hash = hashlib.md5(claim_id.strip().lower().encode()).hexdigest()
        
        # Take substrings to keep them human-readable
        pseudo_id = f"PP-{name_hash[:4].upper()}-U"
        case_reference_id = f"REF-{claim_hash[:4].upper()}-AC"
        return pseudo_id, case_reference_id

    @staticmethod
    def store_mapping(
        db: Session,
        case_ref: str,
        pseudo_pat: str,
        name: str,
        dob: str,
        ssn: str,
        claim_id: str,
        provider_name: str
    ) -> IAMMapping:
        # Check if already exists
        existing = db.query(IAMMapping).filter(IAMMapping.case_reference_id == case_ref).first()
        if existing:
            return existing
        
        mapping = IAMMapping(
            case_reference_id=case_ref,
            pseudo_patient_id=pseudo_pat,
            original_patient_name=name,
            original_dob=dob,
            original_ssn=ssn,
            original_claim_id=claim_id,
            provider_name=provider_name
        )
        db.add(mapping)
        db.commit()
        db.refresh(mapping)
        return mapping

    @staticmethod
    def obfuscate_pii(text: str, name: str, dob: str, ssn: str) -> str:
        cleaned = text
        
        # Redact Name parts
        if name:
            name_parts = name.split()
            for part in name_parts:
                if len(part) > 2:
                    regex = re.compile(rf"\b{re.escape(part)}\b", re.IGNORECASE)
                    cleaned = regex.sub("[REDACTED_PATIENT_NAME]", cleaned)
                    
        # Redact DOB
        if dob:
            cleaned = cleaned.replace(dob, "[REDACTED_PATIENT_DOB]")
            
        # Redact SSN
        if ssn:
            cleaned = cleaned.replace(ssn, "[REDACTED_PATIENT_SSN]")
            
        # Generic patterns for Phone, SSN, Dates
        cleaned = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]", cleaned)
        cleaned = re.sub(r"\b\d{3}-\d{3}-\d{4}\b", "[REDACTED_PHONE]", cleaned)
        cleaned = re.sub(r"\b\(\d{3}\)\s*\d{3}-\d{4}\b", "[REDACTED_PHONE]", cleaned)
        cleaned = re.sub(r"\b\d{2}/\d{2}/\d{4}\b", "[REDACTED_DATE]", cleaned)
        
        return cleaned

    @staticmethod
    def resolve_provider_by_case(db: Session, case_reference_id: str) -> IAMMapping:
        return db.query(IAMMapping).filter(IAMMapping.case_reference_id == case_reference_id).first()
