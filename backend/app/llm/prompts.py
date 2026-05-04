"""
LLM prompt constants.

CONSTRAINTS_BLOCK is injected into the structured context of every LLM call
to keep the model within its allowed task boundaries.

Source of truth: ARCHITECTURE.md §7.3, §7.5.
"""

# Constraint block injected into every structured context.
# Keeps LLM within its allowed task boundaries (ARCHITECTURE.md §7.5).
CONSTRAINTS_BLOCK: list[str] = [
    "Do not authenticate customers.",
    "Do not approve or deny credit.",
    "Do not calculate scores.",
    "Do not modify persistent data.",
    "Do not invent information not present in the structured context.",
    "Return only what is explicitly requested.",
]
