# reeln Examples

Step-by-step walkthroughs for common reeln workflows. Each example is
self-contained — start from the top or jump to whatever fits your use case.

## Getting Started

| # | Example | Description |
|---|---------|-------------|
| 01 | [Getting Started](01-getting-started.md) | Install Python, ffmpeg, and reeln from scratch |
| 02 | [Configuration & OBS Setup](02-configuration.md) | Configure reeln and connect it to your OBS replay buffer |

## Game Workflow

| # | Example | Description |
|---|---------|-------------|
| 03 | [Starting a Game](03-starting-a-game.md) | Initialize a game workspace with teams and sport |
| 04 | [Segments & Events](04-segments-and-events.md) | Process game segments and tag events |
| 05 | [Rendering Shorts](05-rendering-shorts.md) | Turn clips into vertical or square short-form video |
| 06 | [Highlights & Reels](06-highlights-and-reels.md) | Merge segments into highlight reels |
| 07 | [Profiles & Iterations](07-profiles-and-iterations.md) | Reusable render profiles and multi-pass rendering |
| 08 | [Game Finish & Cleanup](08-game-finish-and-cleanup.md) | Finalize games and clean up artifacts |

## Plugins & Advanced

| # | Example | Description |
|---|---------|-------------|
| 09 | [Plugins](09-plugins.md) | Discover, install, and manage plugins |
| 10 | [Smart Zoom](10-smart-zoom.md) | AI-powered tracking that follows the action |

## Prerequisites

- **Python 3.11+** — see [Getting Started](01-getting-started.md) for install options
- **ffmpeg 5.0+** — with libx264, aac, and libass support
- **reeln** — `pip install reeln` or `uv tool install reeln`

If you're a livestreamer using OBS, start with [Configuration & OBS Setup](02-configuration.md)
to connect reeln to your replay buffer output.
