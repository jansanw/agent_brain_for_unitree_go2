---
name: stance
description: Use this skill to change the robot's posture and standing position. Includes standing up, sitting, lying down, and balance modes.
---

# stance

## Overview

Control the Go2 robot's posture and standing state. Use this skill when the user wants the robot to change its body position or stance mode.

## Instructions

### 1. Stand Up

Use the `stance` tool with `pose: "stand_up"`:
- Makes the robot stand up from a lying position
- Example: `{"name": "stance", "arguments": {"pose": "stand_up"}}`

### 2. Balance Stand

Use the `stance` tool with `pose: "balance_stand"`:
- Active balance mode, robot maintains stable posture
- Best for static interactions
- Example: `{"name": "stance", "arguments": {"pose": "balance_stand"}}`

### 3. Sit Down

Use the `stance` tool with `pose: "sit"`:
- Robot sits down on its haunches
- Good for resting or cute interactions
- Example: `{"name": "stance", "arguments": {"pose": "sit"}}`

### 4. Lie Down / Stand Down

Use the `stance` tool with `pose: "stand_down"`:
- Robot lowers to the ground
- Example: `{"name": "stance", "arguments": {"pose": "stand_down"}}`

### 5. Recovery Stand

Use the `stance` tool with `pose: "recovery_stand"`:
- Recovery standing motion
- Use if robot fell down
- Example: `{"name": "stance", "arguments": {"pose": "recovery_stand"}}`

### 6. Stop Moving

Use the `stance` tool with `pose: "stop"`:
- Immediately halt all movement
- Emergency stop command
- Example: `{"name": "stance", "arguments": {"pose": "stop"}}`

### 7. Back Stand

Use the `stance` tool with `pose: "back_stand"`:
- Stand on back legs
- Advanced posture
- Example: `{"name": "stance", "arguments": {"pose": "back_stand"}}`

## Available Poses

| Pose | Description |
|------|-------------|
| `stand_up` | Stand up from lying position |
| `balance_stand` | Active balance standing mode |
| `sit` | Sit down on haunches |
| `stand_down` | Lower to ground |
| `recovery_stand` | Recovery from fallen state |
| `stop` | Emergency stop all motion |
| `back_stand` | Stand on back legs only |

## Examples

| User Request | Tool Call |
|-------------|-----------|
| "站起来" | `stance(pose="stand_up")` |
| "坐下" | `stance(pose="sit")` |
| "趴下" | `stance(pose="stand_down")` |
| "停下" | `stance(pose="stop")` |
| "保持平衡站立" | `stance(pose="balance_stand")` |