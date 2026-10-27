# AI Prompt History and Usage Disclosure

## Purpose

This document records AI assistance used during development of the Inventory Intelligence assessment. It distinguishes available development records from summarized assistance and does not claim to be a complete verbatim transcript.

## AI tools used

- **ChatGPT:** Coding guidance, debugging, validation and test guidance, documentation support, and submission preparation.
- **Other AI tools:** To be completed accurately by the candidate. If none were used, state that none were used.

## Prompt history and development assistance

The following entries summarize the assistance received. They are not verbatim prompts. Exact wording and timestamps should be recovered from the original conversation history wherever available.

### 1. Dataset generator implementation

- **Tool:** ChatGPT
- **Prompt record:** Requested a complete revised version of `src/generator.py` after sharing the existing source file.
- **Areas affected:** `src/generator.py`, generated dataset manifest notes.
- **Verification:** The automated test suite was run after the revision; the latest recorded result was 13 tests passed.

### 2. Dataset validation and integrity checks

- **Tool:** ChatGPT
- **Prompt record:** Requested guidance while developing and validating the synthetic inventory dataset.
- **Areas affected:** Dataset validation, lifecycle validators, reports, and reconciliation checks.
- **Verification:** The latest recorded validation returned PASS, zero issues, and zero baseline reconciliation mismatches.

### 3. Anomaly fixtures and testing

- **Tool:** ChatGPT
- **Prompt record:** Received implementation and testing guidance for anomaly fixtures and inventory validation.
- **Areas affected:** `src/anomaly_injector.py`, `data/ground_truth/`, and automated tests.
- **Verification:** The anomaly fixture test suite previously passed 4 tests. Each anomaly's expected detection must still be checked against the actual assessment requirements.

### 4. Data exports and supporting documentation

- **Tool:** ChatGPT
- **Prompt record:** Received guidance for JSON and SQLite/SQL exports, data documentation, validation reports, and project setup instructions.
- **Areas affected:** `src/export_data.py`, `src/verify_exports.py`, `docs/`, `README.md`, and `requirements.txt`.
- **Verification:** A previous export verification run confirmed row-count agreement across the ten exported tables in CSV, JSON, and SQLite formats.

### 5. Git preparation and submission guidance

- **Tool:** ChatGPT
- **Prompt record:** Received guidance for `.gitignore`, repository status checks, excluding regenerable datasets, and preparing the GitHub submission.
- **Areas affected:** `.gitignore`, repository staging, and submission documentation.
- **Verification:** `git status --short --untracked-files=all` showed the intended source, test, documentation, report, and ground-truth files as untracked, with generated datasets excluded.

## Personal review and validation

The candidate must personally review the implementation and confirm which checks have actually been performed. The latest recorded checks are:

- Full-scale dataset validation: PASS, zero reported issues, zero reconciliation mismatches.
- Automated test suite: 13 passed in 0.60 seconds.
- Anomaly fixture tests: 4 passed in a previous run.
- CSV, JSON, and SQLite export row-count verification: passed in a previous run.

These results do not establish that every required business rule or anomaly detector is complete.

## Known limitations

- Premature transfer detection requires appropriate dispatch and receipt lifecycle data.
- ATP is not exhaustively validated for every inventory balance.
- Anomaly definitions and expected decisions must be checked against the original technical assessment.
- This document is a summarized record, not a complete verbatim prompt transcript.

## Ownership and disclosure

AI assistance was used during development. The candidate is responsible for reviewing the submitted code, understanding its behavior and limitations, verifying the results, and accurately disclosing the assistance used. Any additional AI tools used must be listed.
