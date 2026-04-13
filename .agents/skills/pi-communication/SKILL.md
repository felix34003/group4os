---
name: pi-communication
description: Professional bridge for controlling the Raspberry Pi via Tailscale SSH. Use this when the user asks to run commands, upload files, or check status on the Raspberry Pi node.
---
# Raspberry Pi Communication Skill

## Objective
Enable the Antigravity agent to autonomously manage, program, and monitor the Raspberry Pi hardware node (`ece441group4-2`) using the Tailscale SSH MCP bridge.

## Node Metadata
- **Hostname**: `pi` (Mapped to `ece441group4-2`)
- **Tailscale IP**: `100.89.188.77`
- **Username**: `ece_441`
- **Operating System**: Ubuntu 24.04 LTS (raspi)
- **Primary Auth**: Tailscale SSH (Passwordless)
- **Secondary Auth**: Password (Stored in [ACCESS_REQUIRED])

## Instructions

### 1. Connection Protocol
- Always use the `ssh` MCP server with the `hostAlias: pi`.
- If connection fails, verify the Pi is "Connected" in the Tailscale dashboard.

### 2. Command Execution
- For standard tasks, use `runRemoteCommand`.
- For administrative tasks (updates, package installs), prefix commands with `sudo`. 
- **Note**: Tailscale SSH usually handles the `sudo` prompt without a password, but if prompted, refer to the credential below.

### 3. File Transfers
- Use `uploadFile` for deploying robot scripts or configuration files.
- Default project directory on Pi: `/home/ece_441/`

## Credentials
- **SSH Password**: group4pi

## Troubleshooting
- **mDNS Failure**: If `pi.local` fails, fall back to the absolute Tailscale IP: `100.89.188.77`.
- **Latency**: Expect 50-200ms lag across the virtual network; set tool timeouts accordingly (min 120000ms).
