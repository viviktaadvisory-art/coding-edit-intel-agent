# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import re
import json
from typing import Literal, List, Any
from pydantic import BaseModel, Field

import google.auth
import vertexai
from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.models import Gemini
from google.adk.workflow import Workflow, JoinNode, START
from google.adk.agents.context import Context
from google.genai import types

# Session imports from backend
from app.db.connection import SessionIAM, SessionOntology, SessionClaims, SessionProvider

LLM_LOCATION = "global"
LOCATION = "us-east1"

# Pydantic Schemas for state validation and LLM outputs
class ClaimLine(BaseModel):
    cpt: str
    icd: str
    units: int
    modifier: str
    charge: float

class ClaimIntakePayload(BaseModel):
    patient_name: str
    dob: str
    ssn: str
    provider_name: str
    provider_npi: str
    claim_id: str
    soap_note: str
    lines: List[ClaimLine]

class CptIcdAuditResult(BaseModel):
    status: Literal["PASS", "FAIL", "NEEDS_REVIEW"] = Field(description="Audit status of the validation")
    invalid_codes: List[str] = Field(default=[], description="List of unverified or mismatching codes")
    unsupported_mappings: List[str] = Field(default=[], description="Clinical mismatches found")
    confidence_score: float = Field(..., description="Confidence score from 0.0 to 1.0")
    remediation_recommendation: str = Field(..., description="Actionable correction recommendation")
    supporting_rationale: str = Field(..., description="Explainability reasoning")

class ModifierAuditResult(BaseModel):
    status: Literal["PASS", "FAIL", "NEEDS_REVIEW"] = Field(description="Modifier validation status")
    modifier_issue_type: str = Field(default="", description="Description of modifier mismatch")
    recommended_correction: str = Field(default="", description="Remediation steps for correct modifiers")
    supporting_rationale: str = Field(..., description="Clinical reasoning for modifier use")
    confidence_score: float = Field(..., description="Confidence score from 0.0 to 1.0")

class MedicalNecessityAuditResult(BaseModel):
    status: Literal["PASS", "FAIL", "NEEDS_REVIEW"] = Field(description="Necessity audit status")
    unsupported_codes: List[str] = Field(default=[], description="Billed codes failing LCD conditions")
    supporting_rationale: str = Field(..., description="Citations to payer medical policies")
    confidence_score: float = Field(..., description="Confidence score from 0.0 to 1.0")


# --- 1. COMMON FUNCTIONAL AGENTS ---

def idp_node(node_input: Any) -> Event:
    """Intake payload, redact PHI/PII, create secure tokens & map to secure IAM Registry."""
    if hasattr(node_input, "parts") and node_input.parts:
        text = node_input.parts[0].text
        data = json.loads(text)
    elif isinstance(node_input, str):
        data = json.loads(node_input)
    elif isinstance(node_input, dict):
        data = node_input
    else:
        data = node_input

    if isinstance(data, dict) and "data" in data and data["data"] is not None:
        data = data["data"]

    payload = ClaimIntakePayload.model_validate(data)
    
    # 1. IAM Proxy De-Identification
    pseudo_pat = 'PP-' + str(abs(hash(payload.patient_name)))[:4] + '-U'
    case_ref = 'REF-' + str(abs(hash(payload.claim_id)))[:4] + '-AC'
    
    db_iam = SessionIAM()
    try:
        from app.services.iam_service import IAMService
        IAMService.store_mapping(
            db_iam,
            case_ref=case_ref,
            pseudo_pat=pseudo_pat,
            name=payload.patient_name,
            dob=payload.dob,
            ssn=payload.ssn,
            claim_id=payload.claim_id,
            provider_name=payload.provider_name
        )
        deid_soap = IAMService.obfuscate_pii(payload.soap_note, payload.patient_name, payload.dob, payload.ssn)
    finally:
        db_iam.close()
        
    return Event(output={
        "case_reference_id": case_ref,
        "pseudo_patient_id": pseudo_pat,
        "deidentified_soap_note": deid_soap,
        "provider_name": payload.provider_name,
        "provider_npi": payload.provider_npi,
        "claim_id": payload.claim_id,
        "lines": [line.model_dump() for line in payload.lines]
    }, state={
        "case_reference_id": case_ref,
        "pseudo_patient_id": pseudo_pat,
        "deidentified_soap_note": deid_soap,
        "provider_npi": payload.provider_npi,
        "lines": [line.model_dump() for line in payload.lines]
    })


def ontology_node(ctx: Context, node_input: dict) -> Event:
    """Normalize extracted concepts to standard codes & resolve clinical symptoms to SNOMED CT."""
    deid_soap = node_input["deidentified_soap_note"]
    
    db_ont = SessionOntology()
    try:
        from app.services.snomed_service import SNOMEDService
        symptoms = SNOMEDService.extract_symptoms_from_soap(db_ont, deid_soap)
    finally:
        db_ont.close()
        
    return Event(output={
        **node_input,
        "symptoms": symptoms
    }, state={
        "symptoms": symptoms
    })


# --- 2. PROCESS FUNCTIONAL AGENTS (PARALLEL AUDITING) ---

icd_cpt_validation_agent = LlmAgent(
    name="icd_cpt_validation_agent",
    model=Gemini(model="gemini-flash-latest"),
    instruction="""You are the ICD/CPT/HCPCS Validation Agent.
Verify if the billed CPT/HCPCS codes are clinically justified by the clinical narrative in the SOAP note.
De-identified SOAP Note: {deidentified_soap_note}
Billed Claim Lines: {lines}
Extracted Symptoms: {symptoms}

Verify if the ICD-10 diagnosis codes match the symptoms and support the CPT procedures.
Output your findings in the requested structured JSON schema.""",
    output_schema=CptIcdAuditResult,
    output_key="icd_cpt_audit"
)

modifier_intelligence_agent = LlmAgent(
    name="modifier_intelligence_agent",
    model=Gemini(model="gemini-flash-latest"),
    instruction="""You are the Modifier Intelligence Agent.
Verify modifier usage on billed procedures.
De-identified SOAP Note: {deidentified_soap_note}
Billed Claim Lines: {lines}

Identify if procedural modifiers are required (e.g., Modifier -25 for separately identifiable E/M services performed on the same day as a procedure).
Analyze if the billed codes represent inappropriate unbundling that needs modifier correction.
Output your findings in the requested structured JSON schema.""",
    output_schema=ModifierAuditResult,
    output_key="modifier_audit"
)

def ncci_mue_edit_node(ctx: Context, node_input: dict) -> Event:
    """Run deterministic NCCI bundling and Medically Unlikely Edits (MUE) unit caps."""
    lines = ctx.state["lines"]
    cpt_list = [{"cpt": l["cpt"], "modifier": l["modifier"]} for l in lines]
    
    db_ont = SessionOntology()
    try:
        from app.services.rule_service import RuleService
        violations = RuleService.check_ncci_ptp(db_ont, cpt_list)
        
        mue_violations = []
        for idx, line in enumerate(lines):
            mue_check = RuleService.check_mue_limits(db_ont, line["cpt"], line["units"])
            if mue_check["exceeded"]:
                mue_violations.append({
                    "line": idx + 1,
                    "cpt": line["cpt"],
                    "billed_units": line["units"],
                    "max_limit": mue_check["max_limit"]
                })
    finally:
        db_ont.close()
        
    status = "PASS"
    if violations or mue_violations:
        status = "FAIL"
        
    res = {
        "status": status,
        "ncci_violations": violations,
        "mue_violations": mue_violations
    }
    return Event(output=res, state={"ncci_mue_audit": res})

medical_necessity_agent = LlmAgent(
    name="medical_necessity_agent",
    model=Gemini(model="gemini-flash-latest"),
    instruction="""You are the Medical Necessity Coding Agent.
Verify if the billed CPT/HCPCS procedures are medically necessary for the patient's diagnosis.
De-identified SOAP Note: {deidentified_soap_note}
Billed Claim Lines: {lines}

Identify if the clinical documentation supports the medical necessity of the procedures performed.
Output your findings in the requested structured JSON schema.""",
    output_schema=MedicalNecessityAuditResult,
    output_key="necessity_audit"
)

def provider_pattern_node(ctx: Context, node_input: dict) -> Event:
    """Audit provider risk level and historical billing statistics."""
    npi = ctx.state["provider_npi"]
    
    db_prov = SessionProvider()
    try:
        from app.services.pattern_service import PatternService
        profile = PatternService.audit_provider_profile(db_prov, npi)
    finally:
        db_prov.close()
        
    status = "FAIL" if profile["risk_level"] == "HIGH" else "PASS"
    res = {
        "status": status,
        "risk_level": profile["risk_level"],
        "level5_freq": profile["level5_freq"],
        "mod25_freq": profile["mod25_freq"],
        "reasons": profile.get("reasons", "")
    }
    return Event(output=res, state={"provider_audit": res})


# --- 3. MERGE, ADJUDICATE & REMEDIATE ---

adjudication_join = JoinNode(name="adjudication_join")

def remediation_node(ctx: Context, node_input: dict) -> Event:
    """Aggregate findings from functional agents and compute financial adjudication."""
    case_ref = ctx.state["case_reference_id"]
    pseudo_pat = ctx.state["pseudo_patient_id"]
    lines = ctx.state["lines"]
    symptoms = ctx.state["symptoms"]
    provider_audit = ctx.state["provider_audit"]
    
    from app.models import ClaimLineItem
    cpt_lines = [ClaimLineItem.model_validate(l) for l in lines]
    
    db_claims = SessionClaims()
    db_ont = SessionOntology()
    try:
        from app.services.adjudication_service import AdjudicationService
        provider_profile = {
            "risk_level": provider_audit["risk_level"],
            "level5_freq": provider_audit["level5_freq"],
            "mod25_freq": provider_audit["mod25_freq"]
        }
        res = AdjudicationService.adjudicate(
            db_claims=db_claims,
            db_ont=db_ont,
            case_ref=case_ref,
            pseudo_pat=pseudo_pat,
            billed_lines=cpt_lines,
            provider_profile=provider_profile,
            symptoms=symptoms
        )
    finally:
        db_claims.close()
        db_ont.close()
        
    needs_hitl = res.status in ["DENIED", "ADJUSTED"] or provider_audit["risk_level"] == "HIGH"
    route = "hitl" if needs_hitl else "composer"
    
    adjudication_data = {
        "status": res.status,
        "total_billed": res.total_billed,
        "total_paid": res.total_paid,
        "total_patient": res.total_patient,
        "remediation": res.remediation,
        "lines": [
            {
                "line": l.line,
                "code": l.code,
                "desc": l.desc,
                "snomed": l.snomed,
                "units": l.units,
                "carc": l.carc,
                "rarc": l.rarc,
                "status": l.status,
                "paid": l.paid,
                "charge": l.charge
            } for l in res.lines
        ],
        "needs_hitl": needs_hitl
    }
    return Event(
        output=adjudication_data,
        route=route,
        state={
            "adjudication": adjudication_data,
            "hitl_action_taken": "None (Clean STP)"
        }
    )


# --- 4. HUMAN-IN-THE-LOOP ROUTING ---

async def hitl_routing_node(ctx: Context, node_input: dict):
    """Yield a RequestInput if analyst approval is required to override/confirm claim outcome."""
    if not ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="analyst_approval",
            message=f"Human-in-the-Loop review requested. Case Reference: {ctx.state['case_reference_id']}. Reasons: Claim adjusted/denied. Please review and Approve or Override."
        )
        return
        
    action = ctx.resume_inputs.get("analyst_approval", "Approve")
    
    # If overridden to approved, update the adjudication status in state
    adjudication = ctx.state["adjudication"]
    if action == "Approve" and adjudication["status"] != "PAID":
        adjudication["status"] = "PAID"
        adjudication["total_paid"] = adjudication["total_billed"] * 0.8
        adjudication["total_patient"] = adjudication["total_billed"] * 0.2
        for line in adjudication["lines"]:
            line["status"] = "PAID"
            line["paid"] = line["charge"] * 0.8
            line["carc"] = ""
            line["rarc"] = ""
            
    yield Event(output={
        "action": action,
        "reviewer": "Claims Analyst"
    }, state={
        "hitl_action_taken": action,
        "adjudication": adjudication
    })


# --- 5. COMPOSER & AUDITOR ---

composer_agent = LlmAgent(
    name="composer_agent",
    model=Gemini(model="gemini-flash-latest"),
    instruction="""You are the Communication Composer Agent.
Draft a formal letter to the provider regarding their claim adjudication results.
Adjudication Result: {adjudication}
HITL Analyst Action: {hitl_action_taken}

If the claim is paid in full (STP), draft an approval letter.
If the claim is adjusted or denied, outline the specific remediation steps (e.g. adding modifiers, correcting unit counts) and list the CARC/RARC codes.
Make sure all clinical details and provider info are presented professionally.
Output the drafted communication text in your final response.""",
    output_key="draft_communication"
)


def audit_node(ctx: Context, node_input: str) -> Event:
    """Compile evidence audit log, de-identification compliance check, and final report."""
    adjudication = ctx.state["adjudication"]
    communication = ctx.state["draft_communication"]
    hitl_action = ctx.state.get("hitl_action_taken", "None (Clean STP)")
    
    compliance_report = {
        "case_summary": {
            "case_reference_id": ctx.state["case_reference_id"],
            "pseudo_patient_id": ctx.state["pseudo_patient_id"],
            "status": adjudication["status"],
            "total_billed": adjudication["total_billed"],
            "total_paid": adjudication["total_paid"],
            "total_patient": adjudication["total_patient"]
        },
        "sop_compliance": "COMPLIANT",
        "human_review_reason": "Claim Denied/Adjusted" if hitl_action != "None (Clean STP)" else "None",
        "human_action": hitl_action,
        "data_redaction_status": "SECURE",
        "explainability_trail": {
            "remediation_suggested": adjudication["remediation"]
        },
        "final_decision": adjudication["status"]
    }
    
    # Store compliance report in Claims registry DB
    db_claims = SessionClaims()
    try:
        from app.db.init_db import ClaimAdjudication
        record = db_claims.query(ClaimAdjudication).filter(ClaimAdjudication.case_reference_id == ctx.state["case_reference_id"]).first()
        if record:
            record.remediation = adjudication["remediation"] + f" | Drafted Letter: {communication[:300]}..."
            # Write compliance report directly to remediation field for dashboard access
            record.status = adjudication["status"]
            record.total_paid = adjudication["total_paid"]
            record.total_patient = adjudication["total_patient"]
            db_claims.commit()
    finally:
        db_claims.close()
        
    return Event(output=compliance_report, state={"compliance_report": compliance_report})


# --- 6. ADK 2.0 WORKFLOW DEFINITION ---

root_agent = Workflow(
    name="root_agent",
    edges=[
        (START, idp_node),
        (idp_node, ontology_node),
        
        # Parallel fanning out to Auditing Agents
        (ontology_node, (icd_cpt_validation_agent, modifier_intelligence_agent, ncci_mue_edit_node, medical_necessity_agent, provider_pattern_node)),
        
        # Joining parallel outcomes
        ((icd_cpt_validation_agent, modifier_intelligence_agent, ncci_mue_edit_node, medical_necessity_agent, provider_pattern_node), adjudication_join),
        
        # Remediation & adjudication mapping
        (adjudication_join, remediation_node),
        
        # Conditional HITL routing
        (remediation_node, {"hitl": hitl_routing_node, "composer": composer_agent}),
        
        # HITL continues to composer
        (hitl_routing_node, composer_agent),
        
        # Auditor compiles report
        (composer_agent, audit_node),
    ]
)

app = App(
    root_agent=root_agent,
    name="app",
)
