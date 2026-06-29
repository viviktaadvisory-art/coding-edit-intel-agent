from sqlalchemy.orm import Session
from app.db.init_db import ClaimAdjudication, ClaimLineAdjudication
from app.services.rule_service import RuleService
from app.models import ClaimLineItem, AdjudicationResponse, AdjudicationLineResponse

class AdjudicationService:
    @staticmethod
    def adjudicate(
        db_claims: Session,
        db_ont: Session,
        case_ref: str,
        pseudo_pat: str,
        billed_lines: list,
        provider_profile: dict,
        symptoms: list
    ) -> AdjudicationResponse:
        total_billed = 0.0
        total_paid = 0.0
        total_patient = 0.0
        line_responses = []
        overall_status = "PAID"
        remediation_clauses = []

        # Convert line structures for NCCI check
        cpt_list = [{"cpt": l.cpt, "modifier": l.modifier} for l in billed_lines]
        ncci_violations = RuleService.check_ncci_ptp(db_ont, cpt_list)

        for idx, line in enumerate(billed_lines):
            total_billed += line.charge
            line_status = "PAID"
            line_paid = line.charge
            line_patient = 0.0
            carc = ""
            rarc = ""

            # Check SNOMED CT symptom matching
            matching_snomed = "Not Detected"
            matched = next((s for s in symptoms if s["icd_code"] == line.icd), None)
            if matched:
                matching_snomed = f"{matched['code']} ({matched['term']})"

            # 1. Existence Check
            cpt_ok, cpt_desc, icd_ok, icd_desc = RuleService.validate_code_existence(db_ont, line.cpt, line.icd)
            if not cpt_ok or not icd_ok:
                line_status = "DENIED"
                line_paid = 0.0
                carc = "CO-150"
                rarc = "N386"
                if overall_status != "DENIED":
                    overall_status = "DENIED"
            
            # 2. Medical Necessity LCD Check
            if line_status == "PAID":
                nec_check = RuleService.check_medical_necessity(db_ont, line.cpt, line.icd)
                if not nec_check["valid"]:
                    line_status = "DENIED"
                    line_paid = 0.0
                    carc = "CO-50"
                    rarc = "N115"
                    overall_status = "DENIED"
                    remediation_clauses.append(f"Remove CPT {line.cpt} because it lacks medical necessity for diagnosis {line.icd}.")

            # 3. NCCI PTP Bundling Check
            if line_status == "PAID":
                ncci_violation = next((v for v in ncci_violations if v["line"] == (idx + 1)), None)
                if ncci_violation:
                    line_status = "DENIED"
                    line_paid = 0.0
                    carc = "CO-97"
                    rarc = "M144"
                    if overall_status != "DENIED":
                        overall_status = "ADJUSTED"
                    
                    if ncci_violation.get("bypassable"):
                        remediation_clauses.append(f"Add Modifier -25 to CPT {line.cpt} as documentation supports a separately E/M service.")
                    else:
                        remediation_clauses.append(f"Remove mutually exclusive E/M code CPT {line.cpt}.")

            # 4. MUE Caps Check
            if line_status == "PAID":
                mue_check = RuleService.check_mue_limits(db_ont, line.cpt, line.units)
                if mue_check["exceeded"]:
                    line_status = "ADJUSTED"
                    # Reimburse only up to MUE cap
                    single_charge = line.charge / line.units
                    line_paid = single_charge * mue_check["max_limit"]
                    carc = "CO-198"
                    rarc = "N362"
                    if overall_status != "DENIED":
                        overall_status = "ADJUSTED"
                    remediation_clauses.append(f"Reduce billed units for CPT {line.cpt} from {line.units} to {mue_check['max_limit']} to meet MUE limits.")

            # 5. Provider Pattern / Upcoding Override
            # If provider is high-risk, downcode 99215 to 99212 E/M visit automatically
            if line_status == "PAID" and line.cpt == "99215" and provider_profile["risk_level"] == "HIGH":
                line_status = "ADJUSTED"
                line_paid = 120.00  # Default Level 2 fee
                carc = "CO-150"
                rarc = "N386"
                if overall_status != "DENIED":
                    overall_status = "ADJUSTED"
                remediation_clauses.append(f"Downcode CPT 99215 to CPT 99212 based on low SOAP complexity. Provider NPI audited with upcoding pattern.")

            # Calculate insurance share (80%) vs patient share (20%)
            if line_status in ["PAID", "ADJUSTED"]:
                line_patient = round(line_paid * 0.20, 2)
                line_paid = round(line_paid * 0.80, 2)
            else:
                line_paid = 0.0
                line_patient = 0.0

            total_paid += line_paid
            total_patient += line_patient

            line_responses.append(
                AdjudicationLineResponse(
                    line=idx + 1,
                    code=line.cpt,
                    desc=cpt_desc,
                    snomed=matching_snomed,
                    units=line.units,
                    carc=carc,
                    rarc=rarc,
                    status=line_status,
                    paid=line_paid,
                    charge=line.charge
                )
            )

        # Set final output decision status
        if overall_status == "PAID" and total_paid < total_billed * 0.8:
            overall_status = "ADJUSTED"

        remediation_summary = " ".join(remediation_clauses) if remediation_clauses else "No corrections required. The claim matches clinical documentation and billing guidelines."

        # Write to Claims registry DB
        adjudication_record = db_claims.query(ClaimAdjudication).filter(ClaimAdjudication.case_reference_id == case_ref).first()
        if adjudication_record:
            # Delete old lines
            db_claims.query(ClaimLineAdjudication).filter(ClaimLineAdjudication.adjudication_id == adjudication_record.id).delete()
            # Update record
            adjudication_record.status = overall_status
            adjudication_record.total_billed = total_billed
            adjudication_record.total_paid = total_paid
            adjudication_record.total_patient = total_patient
            adjudication_record.remediation = remediation_summary
        else:
            adjudication_record = ClaimAdjudication(
                case_reference_id=case_ref,
                pseudo_patient_id=pseudo_pat,
                status=overall_status,
                total_billed=total_billed,
                total_paid=total_paid,
                total_patient=total_patient,
                remediation=remediation_summary
            )
            db_claims.add(adjudication_record)
            db_claims.commit()
            db_claims.refresh(adjudication_record)

        # Insert new lines
        for r in line_responses:
            db_line = ClaimLineAdjudication(
                adjudication_id=adjudication_record.id,
                line_number=r.line,
                cpt=r.code,
                cpt_desc=r.desc,
                snomed=r.snomed,
                units=r.units,
                carc=r.carc,
                rarc=r.rarc,
                status=r.status,
                paid=r.paid,
                charge=r.charge
            )
            db_claims.add(db_line)
        db_claims.commit()

        return AdjudicationResponse(
            status=overall_status,
            case_reference_id=case_ref,
            pseudo_patient_id=pseudo_pat,
            total_billed=total_billed,
            total_paid=total_paid,
            total_patient=total_patient,
            lines=line_responses,
            remediation=remediation_summary
        )
