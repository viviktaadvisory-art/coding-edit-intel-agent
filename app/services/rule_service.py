from sqlalchemy.orm import Session
from app.db.init_db import CPTCode, ICD10Code, NCCIPtpEdit, MueCap, MedicalNecessityLcd
from app.models import ClaimLineItem

class RuleService:
    @staticmethod
    def validate_code_existence(db: Session, cpt: str, icd: str) -> tuple:
        cpt_record = db.query(CPTCode).filter(CPTCode.code == cpt).first()
        icd_record = db.query(ICD10Code).filter(ICD10Code.code == icd).first()
        
        cpt_desc = cpt_record.description if cpt_record else "Unknown CPT Code"
        icd_desc = icd_record.description if icd_record else "Unknown ICD-10 Code"
        
        return (cpt_record is not None), cpt_desc, (icd_record is not None), icd_desc

    @staticmethod
    def check_ncci_ptp(db: Session, cpt_list: list) -> list:
        # Check active billed codes for Procedure-to-Procedure bundling issues
        violations = []
        for i, line_a in enumerate(cpt_list):
            for j, line_b in enumerate(cpt_list):
                if i == j:
                    continue
                # Query if CPT A bundles CPT B (CPT A is procedure, CPT B is E/M or bundled code)
                edit = db.query(NCCIPtpEdit).filter(
                    NCCIPtpEdit.cpt_1 == line_a["cpt"],
                    NCCIPtpEdit.cpt_2 == line_b["cpt"]
                ).first()
                
                if edit:
                    # If Modifier 25 is required to bypass, check if it is absent on line B (usually E/M)
                    if edit.modifier_allowed and line_b["modifier"] != "25":
                        violations.append({
                            "line": j + 1,
                            "cpt": line_b["cpt"],
                            "description": edit.description,
                            "bypassable": True,
                            "modifier_required": "25",
                            "status": "FAIL"
                        })
                    elif not edit.modifier_allowed:
                        violations.append({
                            "line": i + 1,
                            "cpt": line_a["cpt"],
                            "description": edit.description,
                            "bypassable": False,
                            "status": "FAIL"
                        })
        return violations

    @staticmethod
    def check_mue_limits(db: Session, cpt: str, units: int) -> dict:
        cap = db.query(MueCap).filter(MueCap.cpt == cpt).first()
        if cap and units > cap.max_units:
            return {
                "exceeded": True,
                "max_limit": cap.max_units,
                "description": f"CPT {cpt} units ({units}) exceed Medically Unlikely Edit cap of {cap.max_units} per day."
            }
        return {"exceeded": False, "max_limit": cap.max_units if cap else 999}

    @staticmethod
    def check_medical_necessity(db: Session, cpt: str, icd: str) -> dict:
        lcd_records = db.query(MedicalNecessityLcd).filter(MedicalNecessityLcd.cpt == cpt).all()
        if not lcd_records:
            return {"valid": True, "description": "No Local Coverage Determination (LCD) policy found. Defaulting to approve."}
        
        # Check if universal wildcard "*" exists
        allowed_icds = [r.icd for r in lcd_records]
        if "*" in allowed_icds:
            return {"valid": True, "description": "CPT code is universally medically necessary."}
            
        if icd in allowed_icds:
            return {"valid": True, "description": f"CPT {cpt} medically necessary for diagnosis {icd} under LCD guidelines."}
            
        return {
            "valid": False,
            "description": f"CPT {cpt} is not approved under LCD guidelines for diagnosis {icd}."
        }
