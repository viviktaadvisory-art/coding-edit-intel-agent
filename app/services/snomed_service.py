from sqlalchemy.orm import Session
from app.db.init_db import SNOMEDMapping

class SNOMEDService:
    @staticmethod
    def extract_symptoms_from_soap(db: Session, deid_soap: str) -> list:
        extracted = []
        soap_lower = deid_soap.lower()
        
        # Query ontology mappings in DB
        mappings = db.query(SNOMEDMapping).all()
        for m in mappings:
            if m.term.lower() in soap_lower:
                extracted.append({
                    "term": m.term,
                    "code": m.code,
                    "label": m.label,
                    "icd_code": m.icd_code
                })
        return extracted
