"""Named comparison thresholds for the validation and fraud agents.

No other module may hardcode these values — import them from here.
"""

# Relative difference abs(a-b)/max(a,b) above which payslip income vs bank deposits is a mismatch.
INCOME_MISMATCH_THRESHOLD = 0.20

# Fraud uses a stricter bar than validation: 20% can be bonus/overtime/timing; 50%+ is hard to explain away.
INCOME_FRAUD_THRESHOLD = 0.50

# Normalized address similarity (0–1) at or above which two addresses are PASS or MINOR_VARIATION, never MISMATCH.
ADDRESS_SIMILARITY_THRESHOLD = 0.85

# Normalized name similarity (0–1) at or above which two names are treated as the same person.
NAME_SIMILARITY_THRESHOLD = 0.90

# Allowed gap (days) between related document periods before a date is called inconsistent.
DATE_TOLERANCE_DAYS = 30
