# SDD Tools Matrix & Implementation Strategy

## Comparative Analysis of AI-Driven Development Tools

| Tool Framework | Type | Implementation Complexity | Key Feature | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| Spek-Kit | Framework | High | Full SDD cycle, GitHub native | Large teams committed to strict SDD |
| **OpenSpec** | **Framework** | **Low** | **Lightweight, classical Spec-Driven** | **Recommended for starting SDD** |
| Kiro | IDE (VSCode Fork) | Low | Native SDD interface (split view) | Agnostic users (no specific IDE pref) |
| BMAD | Framework | High | Agile + SDD integration | Not recommended (overcomplicated) |
| **Cursor Memory Bank** | **Utility** | **Low** | **Context preservation (Memory)** | **Essential for all Cursor users** |
| TaskMaster | Utility | Low | PRD to Task conversion & tracking | Large projects needing task mgmt |
| Tessl | Utility/Repo | Medium | Dynamic context repository | Classical languages (Java/Py/etc) |
| Claude-Flow | Utility/Kit | Medium | Agents, Memory, MCP combination | Claude Desktop & CLI enthusiasts |
| Supercode | Utility (Ext) | Low | Custom Modes restoration, Smart Actions | Must-have extension for Cursor |

## Summary Analysis

1.  **Core Problem**: "Vibe Coding" (unstructured prompting) fails in production due to context loss, lack of standards, and regression issues.
2.  **Solution**: **Spec-Driven Development (SDD)** — a strict workflow where code is a derivative of specifications.
3.  **Strategic Recommendation**:
    *   **Foundation**: Adopt **OpenSpec** for the specification workflow to ensure clarity and structure.
    *   **Memory**: Implement **Cursor Memory Bank** structure to solve the "goldfish memory" problem of AI, ensuring context persists across sessions.
    *   **IDE Enhancement**: Use **Supercode** if using Cursor to streamline the workflow.
