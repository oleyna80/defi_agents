# Universal SDD Workflow

This document outlines the abstract algorithm for Spec-Driven Development (SDD), ensuring production-quality code generation by AI.

## Workflow Overview

The process moves strictly from abstract requirements to concrete code execution. No code is written until the specification and plan are solidified.

### 1. Spec Phase (Specification)

**Goal of this phase**: Define *What* we are building, not *How*.

*   **Input**: User idea, feature request, or bug report.
*   **Action**: Create a Specification file (e.g., `specs/feature-name.md`).
*   **Content**:
    *   **Context**: Why are we doing this? (Business value).
    *   **Requirements**: Functional and non-functional requirements.
    *   **Constraints**: Technology stack, performance limits, security rules.
    *   **User Stories**: Scenarios of usage.
*   **AI Role**: The AI acts as a Product Owner/Architect, helping to refine vague ideas into a rigorous spec.

### 2. Plan Phase (Architecture & Decomposition)

**Goal of this phase**: Define *How* we will build it.

*   **Input**: The approved Specification.
*   **Action**: Create a Technical Plan (e.g., in `docs/plans/` or appended to the spec).
*   **Content**:
    *   **Architecture**: Diagrams, data flow, component interactions.
    *   **File Structure**: interacting files and directories.
    *   **API Design**: Endpoints, signatures, data models.
    *   **Testing Strategy**: How we will verify success.
*   **AI Role**: The AI acts as a Tech Lead, proposing implementations and identifying potential risks.

### 3. Task Phase (Task Slicing)

**Goal of this phase**: Break the plan into atomic, implementable units.

*   **Input**: The Technical Plan.
*   **Action**: Generate a checklist of tasks (e.g., in a task tracker or `todo.md`).
*   **Content**:
    *   Small, isolated steps (e.g., "Create database schema", "Implement API endpoint", "Add validation").
    *   Each task should fit within the AI's context window.
    *   Definition of Done (DoD) for each task.
*   **AI Role**: The AI acts as a Project Manager, prioritizing and organizing the work.

### 4. Code Phase (Generation & Validation)

**Goal of this phase**: Execute the tasks and verify compliance.

*   **Input**: A single Task from the list and the relevant definitions from the Spec/Plan.
*   **Action**: Generate code, run tests, update documentation.
*   **Process**:
    1.  **Context Loading**: AI reads the relevant context (Memory Bank + Spec).
    2.  **Implementation**: AI writes the code.
    3.  **Self-Correction**: AI runs linters/tests and fixes errors.
    4.  **Verification**: Manual or automated check against the original Spec.
*   **AI Role**: The AI acts as a Developer, focused on quality and adherence to strict instructions.
