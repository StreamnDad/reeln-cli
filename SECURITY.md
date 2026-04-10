# Security Policy

## Supported Versions

reeln-cli is pre-1.0 software. Security fixes are published against the
latest release only. We recommend always running the most recent version
from [PyPI](https://pypi.org/project/reeln/) or the
[Releases page](https://github.com/StreamnDad/reeln-cli/releases).

| Version | Supported          |
| ------- | ------------------ |
| 0.0.x (latest) | :white_check_mark: |
| older   | :x:                |

## Scope

reeln-cli is a Python command-line toolkit that runs locally on a
livestreamer's machine. It orchestrates ffmpeg, OBS, and third-party
platform APIs through a plugin system; it does not expose any network
listeners of its own.

In-scope concerns include, but are not limited to:
- Command injection via CLI arguments, config values, or game metadata
  passed to `ffmpeg`, `obs`, or other subprocesses
- Path traversal or unsafe file handling in render queues, output
  directories, or config overrides
- Credential leakage — OAuth tokens, API keys, or refresh tokens written
  to logs, caches, or error messages in plain text
- Unsafe loading or deserialization of state, render queue, or config
  files (JSON / YAML / TOML)
- Arbitrary code execution via the plugin discovery mechanism
- Dependency confusion or typosquatting on the PyPI package name

Out of scope:
- Vulnerabilities in individual plugins (`reeln-plugin-*`) — report those
  to the respective plugin repository
- Vulnerabilities in third-party APIs (YouTube, Meta, TikTok, OpenAI,
  Cloudflare) or in tools reeln-cli invokes (`ffmpeg`, `obs`) — report
  those to the respective project
- Issues that require an attacker to already have local code execution
  on the user's machine or to have supplied a malicious plugin on purpose

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub
issues, discussions, or pull requests.**

Report vulnerabilities using GitHub's private vulnerability reporting:

1. Go to the [Security tab](https://github.com/StreamnDad/reeln-cli/security)
   of this repository
2. Click **"Report a vulnerability"**
3. Fill in as much detail as you can: affected version, reproduction steps,
   impact, and any suggested mitigation

If you cannot use GitHub's reporting, email **git-security@email.remitz.us**
instead.

### What to include

A good report contains:
- The version of reeln-cli and Python you tested against
- Your operating system and architecture (macOS / Windows / Linux, arch)
- Steps to reproduce the issue
- What you expected to happen vs. what actually happened
- The potential impact (credential leakage, code execution, data loss,
  denial of service, etc.)
- Any proof-of-concept code, if applicable

### What to expect

reeln-cli is maintained by a small team, so all timelines below are
best-effort rather than hard guarantees:

- **Acknowledgement:** typically within a week of your report
- **Initial assessment:** usually within two to three weeks, including
  whether we consider the report in scope and our planned next steps
- **Status updates:** roughly every few weeks until the issue is resolved
- **Fix & disclosure:** coordinated with you. We aim to ship a patch
  release reasonably quickly for high-severity issues, with lower-severity
  issues addressed in a future release. Credit will be given in the
  release notes and CHANGELOG unless you prefer to remain anonymous.

If a report is declined, we will explain why. You are welcome to disagree
and provide additional context.
