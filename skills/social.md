---
name: social
description: Use this skill for social interactions and expressions. Includes LED light control and emotional responses.
---

# social

## Overview

Control the Go2 robot's social and expressive features. Use this skill to make the robot more personable and engaging through LED lights and behaviors.

## Instructions

### 1. LED Light Control

Use the `led` tool to change body LED color:
- `color`: Color name (see available colors below)
- `duration`: Duration in seconds

Example: `{"name": "led", "arguments": {"color": "red", "duration": 5}}`

### 2. Available Colors

| Color | Description |
|-------|-------------|
| `white` | White light |
| `red` | Red light |
| `yellow` | Yellow/amber light |
| `blue` | Blue light |
| `green` | Green light |
| `cyan` | Cyan/turquoise light |
| `purple` | Purple/magenta light |

### 3. Social Gestures

Combine LED colors with tricks for expressive interactions:

- Greeting: `hello` trick + white/yellow LED
- Happy: `dance1` or `dance2` + colorful LED
- Love: `show_heart` trick + purple/pink LED
- Alert: Red LED + `stand_up` stance
- Calm: Blue LED + `sit` stance

## Examples

| User Request | Tool Call |
|-------------|-----------|
| "把灯改成红色" | `led(color="red", duration=5)` |
| "闪一下蓝灯" | `led(color="blue", duration=3)` |
| "开心一点" | `dance1 + yellow LED` |
| "我爱你" | `show_heart + purple LED` |