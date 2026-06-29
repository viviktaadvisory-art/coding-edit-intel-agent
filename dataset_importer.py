import os
import json
import pandas as pd

def import_dataset():
    excel_path = os.path.join("data", "synthetic_payer_rcm_coding_edit_intelligence_dataset_Ver1.0.csv.xlsx")
    print(f"Reading dataset from {excel_path}...")
    
    xl = pd.ExcelFile(excel_path)
    
    df_headers = xl.parse("Claims Header")
    df_lines = xl.parse("Claim Lines")
    df_patients = xl.parse("Patients")
    df_providers = xl.parse("Providers")
    df_encounters = xl.parse("Visits Encounters")
    
    # Fill NaN values
    df_headers = df_headers.fillna("")
    df_lines = df_lines.fillna("")
    df_patients = df_patients.fillna("")
    df_providers = df_providers.fillna("")
    df_encounters = df_encounters.fillna("")
    
    eval_cases = []
    
    for _, row in df_headers.iterrows():
        claim_id = str(row["Claim ID"])
        scenario_id = str(row["Scenario ID"])
        member_id = str(row["Member ID"])
        provider_id = str(row["Provider ID"])
        
        # Match patient
        patient_rows = df_patients[df_patients["Member ID"] == member_id]
        if patient_rows.empty:
            print(f"Warning: Patient {member_id} not found for claim {claim_id}")
            continue
        row_patient = patient_rows.iloc[0]
        patient_name = str(row_patient["Synthetic Name"])
        age = int(row_patient["Age"])
        # Mock DOB based on age relative to 2026
        dob = f"{2026 - age}-01-01"
        ssn = f"999-{10 + len(eval_cases):02d}-{1000 + len(eval_cases):04d}"
        
        # Match provider
        provider_rows = df_providers[df_providers["Provider ID"] == provider_id]
        if provider_rows.empty:
            print(f"Warning: Provider {provider_id} not found for claim {claim_id}")
            continue
        row_provider = provider_rows.iloc[0]
        provider_name = str(row_provider["Provider Name"])
        provider_npi = str(int(row_provider["NPI"]))
        
        # Match encounter for clinical note
        encounter_rows = df_encounters[df_encounters["Claim ID"] == claim_id]
        if encounter_rows.empty:
            soap_note = str(row["Narrative"]) # Fallback to claim header narrative
        else:
            soap_note = str(encounter_rows.iloc[0]["Synthetic Clinical Note Summary"])
            
        # Match claim lines
        claim_lines_rows = df_lines[df_lines["Claim ID"] == claim_id]
        lines = []
        for _, line_row in claim_lines_rows.iterrows():
            lines.append({
                "cpt": str(line_row["Procedure Code"]),
                "icd": str(line_row["Primary Diagnosis"]),
                "units": int(line_row["Units"]),
                "modifier": str(line_row["Modifier"]),
                "charge": float(line_row["Line Charge"])
            })
            
        # Build payload matching ClaimIntakePayload schema
        payload = {
            "patient_name": patient_name,
            "dob": dob,
            "ssn": ssn,
            "provider_name": provider_name,
            "provider_npi": provider_npi,
            "claim_id": claim_id,
            "soap_note": soap_note,
            "lines": lines
        }
        
        # Format for ADK EvaluationDataset
        eval_cases.append({
            "eval_case_id": scenario_id,
            "prompt": {
                "role": "user",
                "parts": [
                    {
                        "text": json.dumps(payload, indent=2)
                    }
                ]
            }
        })
        
    dataset_out = {"eval_cases": eval_cases}
    output_path = os.path.join("tests", "eval", "datasets", "basic-dataset.json")
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(dataset_out, f, indent=2)
        
    print(f"Successfully generated {output_path} with {len(eval_cases)} evaluation cases.")

if __name__ == "__main__":
    import_dataset()
