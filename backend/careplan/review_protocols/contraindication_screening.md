---
name: contraindication_screening
description: Use for every order, always — but escalate to an explicit stop-order recommendation when the patient record documents a prior reaction matching one of the drug's listed contraindications.
---

# Contraindication Screening Protocol

1. List every contraindication from the retrieved reference material.
2. For each one, check whether the patient record documents that this exact condition is
   present, absent, or simply not mentioned. Three distinct outcomes, not two:
   - Documented present -> this is an absolute contraindication for this patient.
   - Documented absent -> no issue.
   - Not mentioned -> a screening gap, not a contraindication. Say "not documented," not
     "not contraindicated."
3. If any contraindication is documented as PRESENT, do not soften the language into generic
   "screening needed" boilerplate. State plainly that the order should not proceed as written
   and the prescriber must be contacted before the drug is dispensed.
