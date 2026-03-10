---
name: perception
description: Use this skill when the user asks the robot to look around, adjust its body orientation, or perceive the environment. Includes body tilt control.
---

# perception

## Overview

Control the Go2 robot's body orientation and perception. Use this skill when the user wants the robot to look around or adjust its viewing angle.

## Instructions

### 1. Look Around (Body Tilt)

Use the `look` tool to adjust body orientation:
- `roll`: Tilt left/right (radians)
- `pitch`: Tilt forward/backward (radians)
- `yaw`: Rotate body yaw (radians)

Example: `{"name": "look", "arguments": {"pitch": 0.2}}` - Look down slightly

### 2. Camera Feed

The robot has a front-facing camera. The current frame is available through:
- `get_camera_frame()` - Returns base64 JPEG image

Use the camera to:
- Describe surroundings
- Detect objects
- Check for obstacles

### 3. Obstacle Detection

Check forward obstacle distance:
- `get_forward_obstacle()` - Returns distance in meters
- Robot auto-stops at 0.35m obstacle

### 4. Robot State

Get current robot state with `get_state()`:
- Position (x, y, z)
- Velocity
- Roll/Pitch/Yaw orientation
- Battery level
- Gait type

## Angle Reference

| Direction | Roll | Pitch | Yaw |
|-----------|------|-------|-----|
| Look up | - | -0.3 | - |
| Look down | - | +0.3 | - |
| Tilt left | -0.3 | - | - |
| Tilt right | +0.3 | - | - |

**Note:** Values are in radians. Typical range: -0.5 to +0.5

## Examples

| User Request | Tool Call |
|-------------|-----------|
| "看看下面" | `look(pitch=0.3)` |
| "身体向左倾斜" | `look(roll=-0.2)` |
| "抬头看看" | `look(pitch=-0.2)` |
| "周围有什么" | Use camera + describe |