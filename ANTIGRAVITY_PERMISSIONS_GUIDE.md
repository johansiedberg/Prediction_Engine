# Antigravity Tool Permissions & Auto-Allow Configuration Guide

This guide explains how to configure Antigravity so that bash execution and tool calls run continuously without requiring you to manually click "Allow" (option 4) for every command call.

---

## 1. Enabling Auto-Approve / Always Allow Mode

Antigravity supports auto-approval modes for command and tool execution.

### Option A: Antigravity IDE / Desktop App Settings UI
1. Open **Antigravity Settings** (gear icon in bottom left or top menu).
2. Navigate to **Agent Permissions** / **Execution Safety**.
3. Set **Command Approval Mode** to **Auto-Approve** (or **Always Allow Workspace Commands**).
4. Save settings. Future `run_command` and shell calls in approved sessions will execute automatically.

### Option B: Antigravity Global Config (`~/.gemini/config/config.json`)
You can enable auto-approve mode globally across all projects on your machine by adding the permission flag to `~/.gemini/config/config.json`:

```json
{
  "permissions": {
    "auto_approve_commands": true,
    "allowed_tools": [
      "run_command",
      "replace_file_content",
      "write_to_file",
      "manage_task"
    ]
  }
}
```

### Option C: Antigravity CLI (`agy`) Flag
If running Antigravity from the command line interface:
```bash
agy --auto-approve
# or
agy --yolo
```

---

## 2. Project Rule Enforcement in `.agents/AGENTS.md`

We have integrated permission and workflow governance rules directly into [.agents/AGENTS.md](.agents/AGENTS.md):

* **Direct UI/UX Requests**: Executed directly without plan gating.
* **Collateral UI/UX Changes**: Gated behind an implementation plan review.
* **Goal / Plan Requests**: Require explicit `implementation_plan.md` review and user confirmation (`request_feedback: true`).
* **Autonomous Tool Execution**: Once a plan is approved, the agent batches commands and executes long-running procedures autonomously without turn-by-turn permission prompts.
