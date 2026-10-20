## Mandatory Change Documentation

For every code change, modification, bug fix, refactoring, feature implementation, configuration change, or architectural change you make, you MUST create or update the following two documentation files.

These documentation requirements are mandatory and must not be skipped, even for small changes.

### 1. Change Log — `root_docs/CHANGE_LOG.md`

Document what changed and how the implementation looked before the change.

For every change, include:

- **Change ID:** A unique identifier or sequential number.
- **Date:** Date of the change.
- **Summary:** Brief description of the change and its purpose.
- **Files Modified/Created/Deleted:** List all relevant files and their roles.
- **Previous Implementation:** Explain how the functionality worked before the change, if it existed.
- **New Implementation:** Explain what was implemented and how it works now.
- **Before vs. After:** Clearly describe the differences between the old and new implementations.
- **Reason for Change:** Explain the problem, requirement, or limitation that motivated the change.
- **Impact:** Describe the effects on existing functionality, APIs, data models, dependencies, performance, or other components, as applicable.
- **Tests and Verification:** List tests executed and their actual results. Clearly identify tests that were not run.

If the functionality did not previously exist, explicitly state "New functionality — no previous implementation."

Do not invent or assume details about the previous implementation. Inspect the relevant code and Git history when available. If the previous implementation cannot be established, state that clearly.

### 2. Technical Decision Log — `root_docs/TECHNICAL_DECISIONS.md`

Document the major technical and architectural decisions made while implementing each change.

For every significant decision, include:

- **Decision ID:** A unique identifier or sequential number.
- **Related Change ID:** Link the decision to its corresponding entry in `CHANGE_LOG.md`.
- **Decision:** Clearly state what was decided.
- **Context:** Explain the problem, requirement, or technical constraint that required the decision.
- **Alternatives Considered:** List realistic alternatives considered.
- **Reasoning:** Explain why the selected approach was preferred over the alternatives.
- **Trade-offs:** Describe the benefits, disadvantages, risks, and limitations of the chosen approach.
- **Consequences:** Explain the implications for maintainability, performance, scalability, security, cost, testing, or future development, where applicable.
- **Assumptions and Constraints:** Record important assumptions and technical constraints.

Record decisions that materially affect implementation, architecture, interfaces, data flow, dependencies, error handling, security, performance, or maintainability.

Do not fabricate alternatives or claim that an option was evaluated if it was not. Distinguish actual analysis from retrospective recommendations.

### Documentation Workflow

Follow this workflow for every task:

1. Inspect the relevant existing code and documentation before making changes.
2. Understand and record the previous implementation wherever applicable.
3. Implement the requested change.
4. Run relevant tests and verification checks.
5. Update `root_docs/CHANGE_LOG.md` with the actual changes and before-versus-after comparison.
6. Update `root_docs/TECHNICAL_DECISIONS.md` with the major decisions made during implementation.
7. Verify that both documentation files accurately reflect the final code changes.
8. In your final response, summarize the implementation, tests performed, and documentation entries created or updated.

### Rules

- Maintain these as cumulative logs. Append new entries instead of overwriting or removing historical entries.
- Reuse existing entries and numbering conventions if the files already exist.
- Create the `root_docs/` directory and both files if they do not exist.
- Update both documents in the same task as the corresponding code change.
- If a change has no significant architectural or technical decisions, explicitly record "No significant technical decisions; implementation follows existing project conventions" in the decision log.
- Documentation must describe the code that was actually implemented, not merely the intended implementation.
- Never claim tests, benchmarks, comparisons, or validations were performed unless they actually were.
- Do not modify unrelated historical entries.
- If a task is interrupted before implementation or verification is complete, clearly document its incomplete status rather than claiming completion.
- Treat updating these two documents as part of the definition of done for every code-changing task.

**Definition of Done:** A code-changing task is not complete until the implementation, relevant verification, `docs/CHANGE_LOG.md`, and `docs/TECHNICAL_DECISIONS.md` have all been addressed. If any part cannot be completed, explicitly report the outstanding item and why.