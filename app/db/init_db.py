import sys
import os
from sqlalchemy import Column, Integer, String, Float, Boolean, PrimaryKeyConstraint

# Ensure backend folder is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.connection import (
    iam_engine, IAMBase,
    ontology_engine, OntologyBase,
    claims_engine, ClaimsBase,
    provider_engine, ProviderBase,
    SessionIAM, SessionOntology, SessionClaims, SessionProvider
)

# ==========================================
# 1. ORM SCHEMAS FOR IAM PROXY DB
# ==========================================
class IAMMapping(IAMBase):
    __tablename__ = "iam_mappings"
    id = Column(Integer, primary_key=True, index=True)
    case_reference_id = Column(String, unique=True, index=True)
    pseudo_patient_id = Column(String, index=True)
    original_patient_name = Column(String)
    original_dob = Column(String)
    original_ssn = Column(String)
    original_claim_id = Column(String)
    provider_name = Column(String)

# ==========================================
# 2. ORM SCHEMAS FOR ONTOLOGY DB
# ==========================================
class ICD10Code(OntologyBase):
    __tablename__ = "icd10_codes"
    code = Column(String, primary_key=True)
    description = Column(String)

class SNOMEDMapping(OntologyBase):
    __tablename__ = "snomed_mappings"
    term = Column(String, primary_key=True)
    code = Column(String)
    label = Column(String)
    icd_code = Column(String)

class CPTCode(OntologyBase):
    __tablename__ = "cpt_codes"
    code = Column(String, primary_key=True)
    description = Column(String)

class NCCIPtpEdit(OntologyBase):
    __tablename__ = "ncci_ptp_edits"
    id = Column(Integer, primary_key=True, index=True)
    cpt_1 = Column(String, index=True)
    cpt_2 = Column(String, index=True)
    modifier_allowed = Column(Boolean, default=True)
    description = Column(String)

class MueCap(OntologyBase):
    __tablename__ = "mue_caps"
    cpt = Column(String, primary_key=True)
    max_units = Column(Integer)

class MedicalNecessityLcd(OntologyBase):
    __tablename__ = "medical_necessity_lcds"
    cpt = Column(String)
    icd = Column(String)
    __table_args__ = (PrimaryKeyConstraint("cpt", "icd"),)

# ==========================================
# 3. ORM SCHEMAS FOR CLAIMS REGISTRY DB
# ==========================================
class ClaimAdjudication(ClaimsBase):
    __tablename__ = "claim_adjudications"
    id = Column(Integer, primary_key=True, index=True)
    case_reference_id = Column(String, unique=True, index=True)
    pseudo_patient_id = Column(String, index=True)
    status = Column(String) # PAID, ADJUSTED, DENIED
    total_billed = Column(Float)
    total_paid = Column(Float)
    total_patient = Column(Float)
    remediation = Column(String)

class ClaimLineAdjudication(ClaimsBase):
    __tablename__ = "claim_line_adjudications"
    id = Column(Integer, primary_key=True, index=True)
    adjudication_id = Column(Integer, index=True)
    line_number = Column(Integer)
    cpt = Column(String)
    cpt_desc = Column(String)
    snomed = Column(String)
    units = Column(Integer)
    carc = Column(String)
    rarc = Column(String)
    status = Column(String)
    paid = Column(Float)
    charge = Column(Float)

class ObservabilityLog(ClaimsBase):
    __tablename__ = "observability_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(String)
    type = Column(String)
    message = Column(String)

# ==========================================
# 4. ORM SCHEMAS FOR PROVIDER PROFILES DB
# ==========================================
class ProviderProfile(ProviderBase):
    __tablename__ = "provider_profiles"
    npi = Column(String, primary_key=True)
    provider_name = Column(String)
    level5_freq = Column(Integer)
    mod25_freq = Column(Integer)
    risk_level = Column(String)
    reasons = Column(String)


# ==========================================
# SEEDING EXECUTION
# ==========================================
def seed_databases():
    print("Creating tables on separate SQLite DB files...")
    IAMBase.metadata.create_all(bind=iam_engine)
    OntologyBase.metadata.create_all(bind=ontology_engine)
    ClaimsBase.metadata.create_all(bind=claims_engine)
    ProviderBase.metadata.create_all(bind=provider_engine)
    print("Database tables created successfully.")

    # 1. Seed Ontologies DB
    db_ont = SessionOntology()
    try:
        # Check if already seeded
        if db_ont.query(CPTCode).count() == 0:
            print("Seeding CPT, ICD-10, SNOMED, NCCI, and MUE ontologies...")
            
            # CPT Codes
            cpts = [
                CPTCode(code="99212", description="Office/outpatient visit, established patient, 10 min, straightforward E/M"),
                CPTCode(code="99213", description="Office/outpatient visit, established patient, 15 min, low complexity E/M"),
                CPTCode(code="99214", description="Office/outpatient visit, established patient, 25 min, moderate complexity E/M"),
                CPTCode(code="99215", description="Office/outpatient visit, established patient, 40 min, high complexity E/M"),
                CPTCode(code="17000", description="Destruction of premalignant lesion, first lesion"),
                CPTCode(code="93015", description="Cardiovascular stress test using maximal or submaximal exercise"),
                CPTCode(code="36415", description="Collection of venous blood by venipuncture"),
                CPTCode(code="97110", description="Therapeutic procedure, 1 or more areas, each 15 minutes (physical therapy)")
            ]
            db_ont.add_all(cpts)

            # ICD-10 Codes
            icds = [
                ICD10Code(code="M17.11", description="Unilateral primary osteoarthritis, right knee"),
                ICD10Code(code="L57.0", description="Actinic keratosis (Premalignant skin lesion)"),
                ICD10Code(code="I10", description="Essential (primary) hypertension"),
                ICD10Code(code="Z00.00", description="Encounter for general adult medical examination without abnormal findings"),
                ICD10Code(code="L70.0", description="Acne vulgaris"),
                ICD10Code(code="J30.9", description="Allergic rhinitis, unspecified"),
                ICD10Code(code="R07.9", description="Chest pain, unspecified"),
                ICD10Code(code="I50.9", description="Heart failure, unspecified")
            ]
            db_ont.add_all(icds)

            # SNOMED CT Mappings (User Symptom feedback)
            snomeds = [
                SNOMEDMapping(term="knee pain", code="271801002", label="Knee pain (finding)", icd_code="M17.11"),
                SNOMEDMapping(term="pain in knee", code="271801002", label="Knee pain (finding)", icd_code="M17.11"),
                SNOMEDMapping(term="premalignant lesion", code="302292003", label="Lesion of upper limb skin (finding)", icd_code="L57.0"),
                SNOMEDMapping(term="lesion", code="302292003", label="Skin lesion (finding)", icd_code="L57.0"),
                SNOMEDMapping(term="hypertension", code="38341003", label="Hypertensive disorder (disorder)", icd_code="I10"),
                SNOMEDMapping(term="blood pressure", code="38341003", label="Hypertensive disorder (disorder)", icd_code="I10"),
                SNOMEDMapping(term="routine follow-up", code="185317003", label="Routine follow-up clinical encounter (procedure)", icd_code="Z00.00"),
                SNOMEDMapping(term="acne", code="3282000", label="Acne vulgaris (disorder)", icd_code="L70.0"),
                SNOMEDMapping(term="breakout", code="3282000", label="Acne vulgaris (disorder)", icd_code="L70.0"),
                SNOMEDMapping(term="allergies", code="402630009", label="Allergic rhinitis (disorder)", icd_code="J30.9"),
                SNOMEDMapping(term="seasonal allergies", code="402630009", label="Allergic rhinitis (disorder)", icd_code="J30.9"),
                SNOMEDMapping(term="chest pain", code="29857009", label="Chest pain (finding)", icd_code="R07.9"),
                SNOMEDMapping(term="dyspnea", code="232317003", label="Dyspnea (finding)", icd_code="I50.9"),
                SNOMEDMapping(term="shortness of breath", code="232317003", label="Dyspnea (finding)", icd_code="I50.9")
            ]
            db_ont.add_all(snomeds)

            # NCCI PTP edits
            nccis = [
                NCCIPtpEdit(cpt_1="17000", cpt_2="99213", modifier_allowed=True, description="CPT 17000 bundles E/M visit CPT 99213 unless separately identifiable Modifier -25 is present"),
                NCCIPtpEdit(cpt_1="17000", cpt_2="99214", modifier_allowed=True, description="CPT 17000 bundles E/M visit CPT 99214 unless separately identifiable Modifier -25 is present"),
                NCCIPtpEdit(cpt_1="17000", cpt_2="99215", modifier_allowed=True, description="CPT 17000 bundles E/M visit CPT 99215 unless separately identifiable Modifier -25 is present"),
                NCCIPtpEdit(cpt_1="99214", cpt_2="99213", modifier_allowed=False, description="CPT 99214 and CPT 99213 are mutually exclusive E/M codes billed on same day. Cannot bill together.")
            ]
            db_ont.add_all(nccis)

            # MUE Caps
            mues = [
                MueCap(cpt="99212", max_units=1),
                MueCap(cpt="99213", max_units=1),
                MueCap(cpt="99214", max_units=1),
                MueCap(cpt="99215", max_units=1),
                MueCap(cpt="17000", max_units=1),
                MueCap(cpt="93015", max_units=1),
                MueCap(cpt="36415", max_units=1),
                MueCap(cpt="97110", max_units=2)
            ]
            db_ont.add_all(mues)

            # Medical Necessity LCD pairs
            lcds = [
                MedicalNecessityLcd(cpt="97110", icd="M17.11"),
                MedicalNecessityLcd(cpt="97110", icd="M17.12"),
                MedicalNecessityLcd(cpt="97110", icd="M17.9"),
                MedicalNecessityLcd(cpt="93015", icd="R07.9"),
                MedicalNecessityLcd(cpt="93015", icd="I50.9"),
                MedicalNecessityLcd(cpt="93015", icd="I25.10"),
                MedicalNecessityLcd(cpt="36415", icd="Z00.00"),
                MedicalNecessityLcd(cpt="36415", icd="E11.9"),
                MedicalNecessityLcd(cpt="36415", icd="I10"),
                MedicalNecessityLcd(cpt="17000", icd="L57.0"),
                MedicalNecessityLcd(cpt="17000", icd="D48.5"),
                MedicalNecessityLcd(cpt="99212", icd="*"),
                MedicalNecessityLcd(cpt="99213", icd="*"),
                MedicalNecessityLcd(cpt="99214", icd="*"),
                MedicalNecessityLcd(cpt="99215", icd="*")
            ]
            db_ont.add_all(lcds)

            db_ont.commit()
            print("Ontology DB seeded.")
    finally:
        db_ont.close()

    # 2. Seed Provider Profiles DB
    db_prov = SessionProvider()
    try:
        if db_prov.query(ProviderProfile).count() == 0:
            print("Seeding Provider Profiles...")
            provs = [
                ProviderProfile(
                    npi="1023948571",
                    provider_name="Dr. John Miller, MD",
                    level5_freq=74,
                    mod25_freq=85,
                    risk_level="HIGH",
                    reasons="High upcoding pattern (74% Level 5 office visits) and excessive use of Modifier -25."
                ),
                ProviderProfile(
                    npi="1827364509",
                    provider_name="Dr. Sarah Jenkins, MD",
                    level5_freq=8,
                    mod25_freq=11,
                    risk_level="LOW",
                    reasons="Billing distribution aligns with peer specialty averages."
                )
            ]
            db_prov.add_all(provs)
            db_prov.commit()
            print("Provider Profiles DB seeded.")
    finally:
        db_prov.close()

    print("All databases initialized successfully.")

if __name__ == "__main__":
    seed_databases()
