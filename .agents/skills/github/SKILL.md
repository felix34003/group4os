---
name: github
description: "Comprehensive GitHub management via MCP. Use this for reading repositories, managing issues/PRs, branching, forking, and committing code to GitHub."
---

# GitHub Mastery Skill

Full-lifecycle GitHub management using the Model Context Protocol (MCP).

## Objective
Provide the agent with a standardized workflow for interacting with GitHub repositories, enabling research, codebase modification, and team collaboration.

## Instructions

### 1. Repository Research & Exploration
- **Discovery**: Use `mcp_github_search_repositories` to find relevant projects.
- **Deep Dive**: Use `mcp_github_get_file_contents` to navigate the file tree. Always read `README.md` and manifests (`package.json`, `package.xml`, `requirements.txt`) first.
- **Code Search**: Use `mcp_github_search_code` to find specific implementation patterns or secret keys/configs.

### 2. Code Contribution & Management
- **Branching**: Always create a new branch using `mcp_github_create_branch` before making changes.
- **Single File Update**: Use `mcp_github_create_or_update_file` for quick fixes.
- **Multi-File Commits**: Use `mcp_github_push_files` to bundle related changes (e.g., a logic change and its corresponding test) into a single atomic commit.
- **Forking**: If you lack write access, use `mcp_github_fork_repository` and work within your own namespace.

### 3. Issue & Collaboration Workflow
- **Issue Tracking**: 
    - Use `mcp_github_list_issues` to understand current project status.
    - Use `mcp_github_create_issue` to document bugs or feature requests found during development.
    - Use `mcp_github_add_issue_comment` to provide updates or ask for clarification.
- **Pull Requests**:
    - Use `mcp_github_create_pull_request` to propose changes.
    - Use `mcp_github_get_pull_request_status` to check CI/CD health.
    - Use `mcp_github_merge_pull_request` only after human approval or successful status checks.

### 4. User & Network Analysis
- Use `mcp_github_search_users` to find contributors.
- Use `mcp_github_list_commits` to audit recent changes and understand the project's evolution.

## Best Practices
- **Atomic Commits**: Group related changes. Never commit one file at a time if they are logically connected.
- **Clear Messages**: Use descriptive commit messages and PR titles (e.g., "feat: add Zenoh bridge configuration").
- **Safety First**: Verify the current branch using `mcp_github_list_commits` before pushing destructive changes.

## Troubleshooting
- **Permissions**: If a write operation (create repo, push) fails, inform the user about potential Personal Access Token (PAT) scope issues.
- **Large Repos**: If `mcp_github_get_file_contents` returns too much data, switch to `mcp_github_search_code` to narrow the scope.
