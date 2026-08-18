"""Test script for the LoanIQ LLM Summarizer Agent.

Usage:
    python scripts/test_summarizer.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from orchestrator.agents.summarizer import generate_summary


def main():
    print("==================================================")
    print("         LoanIQ LLM Summarizer Test Runner        ")
    print("==================================================")

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        env_file = root_dir / ".env"
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == "GROQ_API_KEY":
                            api_key = v.strip().strip("'\"")
                            os.environ["GROQ_API_KEY"] = api_key
                            break

    if not api_key or api_key == "gsk_your_groq_api_key_here":
        print("\n[WARNING] GROQ_API_KEY is not set or is using the dummy placeholder.")
        print("Set it in your terminal or in the .env file:")
        print("  GROQ_API_KEY=gsk_...\n")
        print("Proceeding with test — will use deterministic fallback if API call fails.\n")
    else:
        print(f"\n[INFO] GROQ_API_KEY found (starts with: {api_key[:8]}...)")

    # Load example loan file
    example_path = root_dir / "schema" / "loan_file.example.json"
    if not example_path.exists():
        print(f"Error: Sample file not found at {example_path}")
        return

    with open(example_path, "r", encoding="utf-8") as f:
        loan_file = json.load(f)

    print("\n[1/2] Generating summary report for example applicant (Ananya Rao)...")
    summary = generate_summary(loan_file)

    print("\n[2/2] Generated Summary Report:")
    print("--------------------------------------------------")
    print(json.dumps(summary, indent=2))
    print("--------------------------------------------------")

    print("\n[SUCCESS] Test complete!")


if __name__ == "__main__":
    main()
