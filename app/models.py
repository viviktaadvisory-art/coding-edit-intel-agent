from pydantic import BaseModel, Field
from typing import List, Optional

class ClaimLineItem(BaseModel):
    cpt: str = Field(..., description="CPT Procedure or E/M code")
    icd: str = Field(..., description="ICD-10 Diagnosis code")
    units: int = Field(1, ge=1, description="Quantity of services rendered")
    modifier: str = Field("", description="Procedural modifier (e.g. -25, -59)")
    charge: float = Field(..., ge=0.0, description="Amount billed for this line")

class ClaimIntakeRequest(BaseModel):
    patient_name: str = Field(..., description="Patient Full Name (PHI)")
    dob: str = Field(..., description="Patient Date of Birth (PHI)")
    ssn: str = Field(..., description="Patient Social Security Number (PHI)")
    provider_name: str = Field(..., description="Provider Name")
    provider_npi: str = Field(..., description="Provider National Provider Identifier")
    claim_id: str = Field(..., description="Unique claim submission reference")
    soap_note: str = Field(..., description="Doctor's SOAP encounter documentation")
    lines: List[ClaimLineItem] = Field(..., description="Billed line items")

class AdjudicationLineResponse(BaseModel):
    line: int
    code: str
    desc: str
    snomed: str
    units: int
    carc: str
    rarc: str
    status: str
    paid: float
    charge: float

class AdjudicationResponse(BaseModel):
    status: str  # PAID, ADJUSTED, DENIED
    case_reference_id: str
    pseudo_patient_id: str
    total_billed: float
    total_paid: float
    total_patient: float
    lines: List[AdjudicationLineResponse]
    remediation: str

class RemediationRequest(BaseModel):
    case_reference_id: str
    lines: List[ClaimLineItem]

class ProviderNotificationRequest(BaseModel):
    case_reference_id: str

class ProviderNotificationResponse(BaseModel):
    success: bool
    resolved_provider: str
    message_sent: str

class LogResponse(BaseModel):
    timestamp: str
    type: str
    message: str
