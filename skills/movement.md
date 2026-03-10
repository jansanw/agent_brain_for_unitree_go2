---
name: movement
description: Use this skill for robot locomotion commands including walking forward/backward, strafing left/right, and turning.
---

# movement

## Overview

Control the Go2 robot's movement capabilities. Use this skill when the user wants the robot to walk, move around, or navigate.

## Instructions

### 1. Move Forward/Backward

Use the `move` tool to walk forward or backward:
- `x`: Distance in meters (positive = forward, negative = backward)
- Example: `{"name": "move", "arguments": {"x": 2.0}}` - Walk forward 2 meters

### 2. Strafe Left/Right

Use the `move` tool to strafe sideways:
- `y`: Distance in meters (positive = left, negative = right)
- Example: `{"name": "move", "arguments": {"y": 1.0}}` - Strafe left 1 meter

### 3. Turn In Place

Use the `turn` tool to rotate the robot:
- `degrees`: Turning angle (positive = left/counter-clockwise, negative = right/clockwise)
- Example: `{"name": "turn", "arguments": {"degrees": 90}}` - Turn left 90 degrees

### 4. Set Walking Speed

Use the `set_speed` tool to adjust walking speed:
- `level`: 0 = slow, 1 = normal, 2 = fast

## Safety Notes

- The robot will automatically stop if it detects an obstacle within 0.35m while moving forward
- Always ensure the area is clear before commanding movement
- Use appropriate speed level based on environment

## Examples

| User Request | Tool Call |
|-------------|-----------|
| "向前走2米" | `move(x=2.0)` |
| "后退1米" | `move(x=-1.0)` |
| "向左平移半米" | `move(y=0.5)` |
| "向右转90度" | `turn(degrees=-90)` |
| "向左转180度" | `turn(degrees=180)` |