---
name: trick
description: Use this skill to perform special moves and acrobatic tricks. Includes greetings, dance, flips, jumps, and other impressive movements.
---

# trick

## Overview

Make the Go2 robot perform impressive tricks and special movements. These are predefined motion sequences that showcase the robot's agility and personality.

## Instructions

### 1. Greeting Gestures

Use the `trick` tool with `name: "hello"`:
- Friendly waving gesture
- Good for greetings
- Example: `{"name": "trick", "arguments": {"name": "hello"}}`

### 2. Stretch

Use the `trick` tool with `name: "stretch"`:
- Stretching motion
- Good for showing relaxation
- Example: `{"name": "trick", "arguments": {"name": "stretch"}}`

### 3. Dance Moves

Use `name: "dance1"` or `name: "dance2"`:
- Two different dance routines
- Fun for entertainment
- Example: `{"name": "trick", "arguments": {"name": "dance1"}}`

### 4. Acrobatic Flips

**Advanced tricks requiring space:**
- `front_flip`: Forward flip
- `back_flip`: Backward flip
- `left_flip`: Left side flip
- `right_flip`: Right side flip

**Warning:** These require adequate space and soft surface.

### 5. Jumps

- `front_jump`: Jump forward
- `front_pounce`: Pounce forward aggressively

### 6. Other Tricks

- `wiggle_hips`: Wiggle hips playfully
- `scrape`: Scraping motion
- `wallow`: Rolling motion
- `show_heart`: Show heart gesture (比心)
- `handstand`: Handstand on front legs

## Available Tricks

| Trick | Description | Duration |
|-------|-------------|----------|
| `hello` | Wave greeting | ~3s |
| `stretch` | Stretch body | ~3s |
| `wiggle_hips` | Wiggle hips | ~3s |
| `scrape` | Scrape ground | ~3s |
| `wallow` | Roll around | ~5s |
| `show_heart` | Heart gesture | ~3s |
| `dance1` | Dance routine 1 | ~10s |
| `dance2` | Dance routine 2 | ~10s |
| `front_flip` | Forward flip | ~5s |
| `back_flip` | Backward flip | ~5s |
| `left_flip` | Left side flip | ~5s |
| `right_flip` | Right side flip | ~5s |
| `handstand` | Handstand | ~5s |
| `front_jump` | Jump forward | ~3s |
| `front_pounce` | Pounce forward | ~3s |

## Safety Notes

- Ensure adequate space for flips and jumps
- Soft surface recommended for acrobatic tricks
- Robot must be in standing position before tricks

## Examples

| User Request | Tool Call |
|-------------|-----------|
| "打个招呼" | `trick(name="hello")` |
| "跳个舞" | `trick(name="dance1")` |
| "比个心" | `trick(name="show_heart")` |
| "做个前空翻" | `trick(name="front_flip")` |
| "扭扭腰" | `trick(name="wiggle_hips")` |