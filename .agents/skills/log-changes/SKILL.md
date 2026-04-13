---
name: log-changes
description: Automates the creation of a timestamped change log within a dedicated 'change_logs/' subdirectory of the active project. Use this when the user asks to "log changes" or "log our work".
---
# Log Changes Skill

This skill allows the agent to systematically document all file modifications, architectural changes, and the rationale behind them in a structured log.

## Objective
To maintain a historical record of project evolution, facilitating easier debugging, collaboration, and architectural review.

## Instructions

1. **Analyze History**: Review the recent conversation history to identify all file creations and modifications.
2. **Determine Scope**: identify the primary active project directory.
3. **Directory Check**: Ensure a `change_logs/` subdirectory exists within that active project directory. Create it if it is missing.
4. **Generate Timestamp**: Use the system time to generate a filename in the format: `change-log-YYYYMMDD_HHMMSS.md`.
5. **Write Log Content**: Create the log file inside the `change_logs/` folder with the following structure:
    - **Header**: "Change Log - [Date/Time]"
    - **Summary Table**:
        | File | Type of Change (New/Modify/Delete) | Description of Change | Rationale |
        | :--- | :--- | :--- | :--- |
    - **Architectural Impact**: A brief paragraph explaining how these changes shift or reinforce the overall system design.
6. **Confirmation**: Notify the user once the log file has been created and provide a clickable link to it.

## When to use this skill
- Use this skill whenever the user says "log our changes", "save a change log", or "document what we've done".
- Also recommend using this skill after significant architectural milestones.
