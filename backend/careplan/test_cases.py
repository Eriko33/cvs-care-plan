"""Fixed test cases of increasing complexity, used by `run_eval_suite`.

Each case carries what a fully-automated check can verify on its own
(dose_per_kg for math-checking, expected_keywords for a coarse coverage
proxy) without needing manual ClaimAnnotation review. This is NOT a
replacement for the manual Precision/Recall workflow (evaluation.py) — it's
a fast regression check you can run on every prompt change; real hallucination
review still needs a human reading the output against the reference material.
"""

CASE_SIMPLE = {
    "name": "simple_mg_ivig",
    "dose_per_kg": 2.0,
    "expected_keywords": ["IgA", "contraindicat", "FVC", "monitor"],
    "data": {
        "patient_name": "A.B.",
        "patient_dob": "1979-06-08",
        "mrn": "001234",
        "weight": "72 kg",
        "allergies": "None known",
        "primary_diagnosis": "G70.00 Generalized myasthenia gravis",
        "drug_name": "IVIG (Privigen)",
        "home_meds": "Pyridostigmine 60mg q6h PRN, Prednisone 10mg daily, Lisinopril 10mg daily, Omeprazole 20mg daily",
        "patient_records": (
            "Baseline clinic note (pre-infusion)\nDate: 2026-08-14\n"
            "Vitals: BP 128/78, HR 78, RR 16, SpO2 98% RA, Temp 36.7C\n"
            "Exam: Ptosis bilateral, fatigable proximal weakness (4/5), speech slurred after repeated counting, "
            "no respiratory distress.\n"
            "Labs: CBC WNL; BMP: Na 138, K 4.1, Cl 101, HCO3 24, BUN 12, SCr 0.78, eGFR >90.\n"
            "IgG baseline: 10 g/L.\nBaseline FVC 2.8 L (predicted 4.0 L; ~70% predicted).\n"
            "Plan: IVIG 2 g/kg total (144 g for 72 kg) given as 0.4 g/kg/day x 5 days.\n"
            "Premedicate with acetaminophen + diphenhydramine."
        ),
        "provider_name": "Dr. Michael Chen",
        "npi": "1234567890",
    },
}

CASE_MEDIUM = {
    "name": "medium_mg_mild_ckd_nsaid_interaction",
    "dose_per_kg": 2.0,
    "expected_keywords": ["ibuprofen", "NSAID", "renal", "contraindicat"],
    "data": {
        "patient_name": "E.F.",
        "patient_dob": "1990-11-02",
        "mrn": "002345",
        "weight": "60 kg",
        "allergies": "Codeine (nausea)",
        "primary_diagnosis": "G70.00 Generalized myasthenia gravis; also N18.2 CKD stage 2, I10 Essential hypertension",
        "drug_name": "IVIG (Privigen)",
        "home_meds": "Pyridostigmine 60mg q6h PRN, Prednisone 10mg daily, Lisinopril 10mg daily, Ibuprofen 400mg PRN, Omeprazole 20mg daily",
        "patient_records": (
            "Baseline clinic note (pre-infusion)\nDate: 2026-09-01\n"
            "Vitals: BP 138/86, HR 82, RR 16, SpO2 98% RA, Temp 36.8C\n"
            "Exam: Ptosis bilateral, fatigable proximal weakness (4/5), no respiratory distress.\n"
            "Labs: BMP: Na 139, K 4.4, Cl 102, HCO3 24, BUN 18, SCr 1.1 (mild elevation), eGFR 65 (CKD stage 2).\n"
            "IgG baseline: 11 g/L.\nBaseline FVC 3.0 L (predicted 4.0 L; ~75% predicted).\n"
            "Plan: IVIG 2 g/kg total (120 g for 60 kg) given as 0.4 g/kg/day x 5 days."
        ),
        "provider_name": "Dr. Michael Chen",
        "npi": "1234567890",
    },
}

CASE_COMPLEX = {
    "name": "complex_5dx_8meds_interactions",
    "dose_per_kg": 2.0,
    "expected_keywords": ["metformin", "thrombo", "warfarin", "amiodarone", "hyperkalemia", "IgA"],
    "data": {
        "patient_name": "C.D.",
        "patient_dob": "1958-03-22",
        "mrn": "005678",
        "weight": "68 kg",
        "allergies": "Penicillin (urticaria); Sulfonamides (rash)",
        "primary_diagnosis": (
            "G70.00 Generalized myasthenia gravis (primary); also: N18.32 CKD stage 3b, "
            "I10 Essential hypertension, E11.9 Type 2 diabetes mellitus, I48.91 Atrial fibrillation"
        ),
        "drug_name": "IVIG (Privigen)",
        "home_meds": (
            "Pyridostigmine 60mg PO q6h PRN, Prednisone 10mg PO daily, Warfarin 5mg PO daily, "
            "Amiodarone 200mg PO daily, Metformin 500mg PO BID, Lisinopril 10mg PO daily, "
            "Furosemide 20mg PO daily, Omeprazole 20mg PO daily"
        ),
        "patient_records": (
            "Baseline clinic note (pre-infusion)\nDate: 2026-09-10\n"
            "Vitals: BP 148/92, HR 92 (irregularly irregular), RR 18, SpO2 96% RA, Temp 36.8C\n"
            "Exam: Ptosis bilateral, fatigable proximal weakness (4/5), mild dysarthria after sustained speech, "
            "no acute respiratory distress.\n"
            "Labs: BMP: Na 137, K 5.4 (H), Cl 100, HCO3 22, BUN 34 (H), SCr 1.8 (H), eGFR 38 (CKD stage 3b).\n"
            "Glucose 186 (H), HbA1c 8.2% (H).\n"
            "INR 3.4 (H) - supratherapeutic, patient on warfarin + amiodarone concurrently.\n"
            "IgG baseline: 9.5 g/L.\nBaseline FVC 2.1 L (predicted 3.6 L; ~58% predicted).\n"
            "Plan: IVIG 2 g/kg total (136 g for 68 kg) given as 0.4 g/kg/day x 5 days.\n"
            "Premedicate with acetaminophen + diphenhydramine."
        ),
        "provider_name": "Dr. Michael Chen",
        "npi": "1234567890",
        "max_tokens": 12000,
    },
}

CASE_CONTRAINDICATION = {
    "name": "edge_documented_prior_anaphylaxis",
    "dose_per_kg": 2.0,
    "expected_keywords": ["anaphyla", "contraindicat", "hold", "do not"],
    "data": {
        "patient_name": "G.H.",
        "patient_dob": "1970-01-15",
        "mrn": "009988",
        "weight": "80 kg",
        "allergies": "IVIG/immune globulin - prior anaphylactic reaction (2019); Penicillin - rash",
        "primary_diagnosis": "G70.00 Generalized myasthenia gravis",
        "drug_name": "IVIG (Privigen)",
        "home_meds": "Pyridostigmine 60mg q6h PRN, Prednisone 10mg daily",
        "patient_records": (
            "Baseline clinic note (pre-infusion)\nDate: 2026-09-15\n"
            "Vitals: BP 122/76, HR 74, RR 16, SpO2 99% RA, Temp 36.6C\n"
            "Exam: Mild ptosis, proximal weakness (4+/5).\n"
            "History: Documented anaphylactic reaction to IVIG infusion in 2019 (per prior hospital records) — "
            "required epinephrine and ICU observation.\n"
            "Plan: IVIG 2 g/kg total (160 g for 80 kg) given as 0.4 g/kg/day x 5 days."
        ),
        "provider_name": "Dr. Michael Chen",
        "npi": "1234567890",
    },
}

TEST_CASES = [CASE_SIMPLE, CASE_MEDIUM, CASE_COMPLEX, CASE_CONTRAINDICATION]
