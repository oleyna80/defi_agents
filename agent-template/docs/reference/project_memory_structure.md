# Project Memory Structure (Cursor Memory Bank)

To implement the Memory Bank pattern effectively, we establish a dedicated directory structure that serves as the "Long-Term Memory" for the AI. This ensures context is preserved across sessions and context clears.

## Directory Location

Recommended path: `docs/memory-bank/` (or `.cursor/memory/`)

## Core Files Structure

The Memory Bank consists of live documents that are updated as the project evolves.

### 1. `productContext.md` (The "Why")
*   **Purpose**: Stores the high-level vision and business context.
*   **Contents**:
    *   Project Glossary.
    *   User personas and stories.
    *   Business constraints and goals.
    *   "Big Picture" view of the product.

### 2. `activeContext.md` (The "Now")
*   **Purpose**: Tracks the current state of development sessions.
*   **Contents**:
    *   Current Focus: What is being worked on *right now*.
    *   Recent Changes: Summary of the last few commits/features.
    *   Next Steps: Immediate upcoming tasks.
    *   Active Decisions: Context for ongoing discussions.

### 3. `systemPatterns.md` (The "How")
*   **Purpose**: Captures architectural decisions and standards.
*   **Contents**:
    *   Architecture diagrams (Mermaid or text descriptions).
    *   Design patterns in use (e.g., "Repository Pattern", "Functional Components").
    *   Tech Stack details.
    *   Code style guidelines and conventions.

### 4. `progress.md` (The "Status")
*   **Purpose**: A high-level roadmap and status tracker.
*   **Contents**:
    *   Milestones (Completed vs Pending).
    *   Feature status (Planned, In Progress, Done).
    *   Known Issues / Technical Debt.

## Usage Rules

To maintain the integrity of the Memory Bank, add these rules to `.cursor/rules/memory-bank.mdc` (or your system instruction):

1.  **Read First**: At the start of every session, read `activeContext.md` and `productContext.md`.
2.  **Update Frequently**: When a task is completed, update `progress.md` and `activeContext.md`.
3.  **Document Decisions**: If a major architectural decision is made, record it in `systemPatterns.md` immediately.
4.  **No Hallucinations**: Do not assume context that isn't in these files; ask the user if uncertain.
