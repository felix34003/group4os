---
name: use-wsl
description: Standardizes the use of the WSL MCP server for repository management, script execution, and Linux-based development workflows.
---

# Use WSL Skill

This skill provides a standardized approach for using the `wsl` MCP server to interact with the Linux subsystem. It ensures consistent path mapping, reliable command execution, and efficient repository management.

## Objective
To streamline development tasks that require a Linux environment, such as running specific build tools, executing shell scripts, or performing Git operations within WSL.

## Core Instructions

### 1. File System Navigation
- **Windows Integration**: Access the Windows workspace via the `/mnt/c/` mount point.
- **Project Root**: The default project path is `/mnt/c/Users/imete/Desktop/felixWarehouseRobot`.
- **Tool Mapping**: Always verify the current working directory in WSL using `mcp_wsl_execute_command(command="pwd", working_dir="/mnt/c/...")`.

### 2. Command Chaining (CRITICAL)
- **Problem**: The `mcp_wsl_execute_command` tool may strip or incorrectly interpret shell operators like `&&`, `||`, or `;` when passed directly.
- **Solution**: To run multiple commands in a single call, wrap the entire command string in `bash -c`.
    - **Incorrect**: `git pull && colcon build`
    - **Correct**: `bash -c "git pull && colcon build"`
- **Alternative**: For complex workflows, write a temporary `.sh` script using `write_to_file` on the Windows side, then execute it in WSL.

### 3. Repository Management
- **Git Operations**: Run `git` commands directly within the WSL environment to maintain Linux compatibility for line endings and permissions.
- **Example**: `mcp_wsl_execute_command(command="git status", working_dir="/mnt/c/Users/imete/Desktop/felixWarehouseRobot")`.

### 4. Running Scripts
- **Python**: Use `python3` for all Python-based scripts.
- **Bash**: Ensure scripts have at least `+x` permissions before execution.
    - **Example**: `mcp_wsl_execute_command(command="chmod +x script.sh && ./script.sh")`. (Note: use `bash -c` if chaining).

## When to Use This Skill
- When the user asks to "pull code", "run a script in WSL", or "check Linux environment info".
- When building or testing components that are known to have Linux dependencies (e.g., ROS 2 nodes).
- When resolving issues related to case-sensitivity or file permissions that differ between Windows and Linux.

## Verification Workflow
- Always confirm success by checking the `Exit Code` of the `mcp_wsl_execute_command` call. An exit code of `0` indicates SUCCESS.
- Use `mcp_wsl_get_directory_info` to verify that command outputs (like new build folders) were actually created.
