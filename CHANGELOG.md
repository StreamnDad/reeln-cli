# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `reeln queue` command group for staged render-then-publish workflow: list, show, edit, publish, publish-all, remove, targets
- `--queue` / `-q` flag on `render short` and `render apply` — renders but queues for review instead of publishing immediately
- Per-target publish tracking — publish to YouTube, review, then selectively push to Instagram/TikTok without re-rendering
- `ON_QUEUE` and `ON_PUBLISH` lifecycle hooks for plugin integration with the queue workflow
- Centralized metadata generation (`core/metadata.py`) — auto-generates title and description from game/event context
- `QueueItem` stores config profile name — `queue publish` loads the same plugin settings used at queue time
- Queue persistence via `render_queue.json` (per-game directory) with advisory central index for cross-game listing
- `QueueError` exception class for queue operation errors

## [0.0.37] - 2026-04-03

### Added
- `reeln game list` — list games in output directory with status badges (finished/in progress)
- `reeln game info` — show detailed game information (teams, venue, progress, livestreams)
- `reeln game delete` — delete a game directory with confirmation prompt (`--force` to skip)
- Colored CLI output: `--version`, `plugins list`, `plugins search`, `plugins info`, `plugins inputs`, `game list`, `game info`, `game delete` all use consistent styled output (bold names, green/red/yellow badges, dim labels)
- Shared `reeln.commands.style` module for consistent CLI formatting
- Plugin Input Contributions: plugins declare additional user inputs via `input_schema` class attribute (`PluginInputSchema`, `InputField`)
- `--plugin-input KEY=VALUE` (`-I`) repeatable option on `game init`, `render short`, and `render preview`
- Interactive prompts for plugin-contributed inputs (questionary-based, preset-first pattern)
- Conditional prompting: `thumbnail` and `tournament` only prompted when a plugin declares them
- `InputCollector` with conflict resolution (same-type dedup, cross-type namespacing)
- `get_input_schema()` method support: plugins can conditionally declare inputs based on feature flags (e.g., only prompt for thumbnail when `create_livestream` is enabled)
- Registry fallback: plugins without `input_schema` / `get_input_schema()` get inputs from `ui_contributions.input_fields` in registry JSON
- `reeln plugins inputs` introspection command (text + JSON output for reeln-dock)
- `input_contributions` field on `RegistryEntry` model, parsed from `ui_contributions.input_fields`
- Google plugin registry entry updated with `thumbnail_image` input field for `game_init`

### Changed
- `init_game()` accepts `plugin_inputs` kwarg, included in `ON_GAME_INIT` / `ON_GAME_READY` hook data
- `PRE_RENDER` / `POST_RENDER` hook data includes `plugin_inputs` when present
- `activate_plugins()` now registers plugin input schemas with the `InputCollector` singleton
- `game init` checks for unfinished games **before** interactive prompts (fail fast instead of prompting then failing)
- `_resolve_game_dir` now sorts by `created_at` from `game.json` instead of filesystem mtime (which is unreliable due to Spotlight/Time Machine)
- `_resolve_game_dir` prefers unfinished games over finished ones, so `reeln game finish` finds the right game

## [0.0.36] - 2026-04-02

### Fixed
- Read the Docs example page links now navigate correctly (renamed wrapper files to match example filenames)

## [0.0.35] - 2026-04-02

### Added
- `examples/` directory with 10 step-by-step walkthrough pages covering install, OBS setup, game lifecycle, rendering, profiles, plugins, and smart zoom
- Examples integrated into Read the Docs via `docs/examples/` section
- Video demo talking points (gitignored, presenter-only)

### Changed
- README.md rewritten: prominent ffmpeg dependency callout, updated CLI reference (removed stale "coming soon" section), added examples link
- Docs index updated with ffmpeg admonition, current feature list, and examples toctree entry

## [0.0.34] - 2026-04-02

### Added
- `reeln hooks run` and `reeln hooks list` CLI commands for non-interactive hook execution (JSON-in/JSON-out, designed for reeln-dock integration)
- `reeln-native` v0.2.0 as a required dependency (Rust-powered acceleration)
- `native-dev` and `plugins` Makefile targets for local development

### Changed
- Goal overlay layout: dynamic box height when assists are present, adjusted assist Y-coordinates for better spacing
- `probe_duration()` now accepts single-arg form with auto-discovery (`probe_duration(path)`)
- Overlay template documentation now covers ASS templates only (JSON templates deferred to native migration)

### Removed
- Dead PNG overlay pipeline (`ResolvedOverlay`, `resolve_overlay_for_profile`, `composite_video_overlay`) — unreachable code from incomplete JSON template integration
- `goal_overlay.json` template (nothing loaded it)
- Shell completion Makefile targets (replaced by symlink install)

## [0.0.33] - 2026-03-23

### Added
- Branding overlay on rendered shorts: shows "reeln v{version} by https://streamn.dad" with a black-bordered white text at the top of the video for the first ~5 seconds with a smooth fade-out — enabled by default, configurable via `branding` config section, disable with `--no-branding` CLI flag
- `BrandingConfig` model (`enabled`, `template`, `duration`) for per-user branding customization
- Bundled `branding.ass` ASS template with `\fad(300,800)` animation and black outline for visibility over any background
- `--no-branding` flag on `render short` and `render preview` commands
- Branding renders only on the first iteration in multi-iteration mode
- Cross-fade transitions between iterations: uses ffmpeg `xfade` + `acrossfade` filters for smooth 0.5s fade transitions instead of hard cuts, with automatic fallback to concat demuxer if xfade fails
- Smart zoom support in the iteration pipeline: `--smart --iterate` now extracts frames once upfront and passes the zoom path through to each iteration's `plan_short()` call
- `speed_segments` in render profiles for variable speed within a single clip — e.g., normal speed → slow motion → normal speed, using the proven split/trim/concat ffmpeg pattern
- `--player-numbers` (`-n`) flag on `render short`, `render preview`, and `render apply` for roster-based player lookup: accepts comma-separated jersey numbers (e.g., `--player-numbers 48,24,2`), looks up names from the team roster CSV, and populates goal scorer and assist overlays automatically
- `--event-type` flag on render commands for scoring team resolution: `HOME_GOAL`/`AWAY_GOAL` determines which team's roster to look up
- `RosterEntry` data model and `load_roster()` / `lookup_players()` / `resolve_scoring_team()` core functions for roster management
- `GameInfo` now persists `level`, `home_slug`, and `away_slug` when `game init --level` is used, enabling roster lookup during rendering
- `build_overlay_context()` accepts optional `scoring_team` parameter to override the default (home team)
- Smart target zoom (`--crop smart`): extracts frames from clips, emits `ON_FRAMES_EXTRACTED` hook for vision plugins (e.g. reeln-plugin-openai) to detect action targets, then builds dynamic ffmpeg crop expressions that smoothly pan across detected targets
- `ZoomPoint`, `ZoomPath`, and `ExtractedFrames` data models for smart zoom contracts
- `ON_FRAMES_EXTRACTED` lifecycle hook for plugins to analyze extracted video frames
- `extract_frames()` method on the Renderer protocol and FFmpegRenderer for frame extraction
- `build_piecewise_lerp()` and `build_smart_crop_filter()` for dynamic ffmpeg crop expressions
- `--zoom-frames` option on `render short` and `render preview` (default 5, range 1-20)
- Zoom debug output: `debug/zoom/zoom_path.json` and frame symlinks when `--debug` is used with smart crop
- Smart pad mode (`--crop smart_pad`): follows action vertically like smart zoom but keeps black bars instead of filling the entire frame — falls back to static pad when no vision plugin provides data
- `build_smart_pad_filter()` for dynamic vertical pad positioning based on zoom path center_y
- Debug crosshair annotations: extracted frames in `debug/zoom/` now include annotated copies with green crop box and red crosshair overlays showing detected center points
- `--scale` option on `render short` and `render preview` (0.5-3.0, default 1.0): zooms in by scaling up the intermediate frame before crop/pad — works with all crop modes including smart tracking
- `--smart` flag on `render short` and `render preview`: enables smart tracking via vision plugin as an orthogonal option, composable with `--crop pad|crop` and `--scale`
- `build_overflow_crop_filter()` for pad + scale > 1.0: crops overflow after scale-up before padding
- Automatic fallback from smart crop to center crop (or smart_pad to static pad) when no vision plugin provides zoom data
- `--no-enforce-hooks` global CLI flag to temporarily disable registry-based hook enforcement for plugins
- `game finish` now relocates segment and highlights outputs from the shared output directory into `game_dir/outputs/`, preventing file collisions across multiple games per day
- `game init` now blocks with a clear error if an unfinished game exists — run `reeln game finish` first
- `GameState` tracks `segment_outputs` and `highlights_output` for file relocation
- `find_unfinished_games()` helper scans for active game directories
- `relocate_outputs()` helper moves output files into the game directory
- `reeln doctor` now collects and runs health checks from plugins that implement `doctor_checks()`
- `doctor` capability added to plugin duck-type detection
- `--tournament` CLI flag on `game init` for optional tournament name/context — flows through to plugins via hook context and overlay templates
- `tournament` and `level` fields now included in template context (`build_base_context()`), available as `{{tournament}}` and `{{level}}` in ASS subtitle templates

### Changed
- Scale, framing (crop/pad), and smart tracking are now orthogonal axes — any combination works without dedicated enum values
- Short/preview renders now output to a `shorts/` subdirectory by default (e.g., `period-2/shorts/clip_short.mp4`) to prevent segment merges from picking up rendered files

### Deprecated
- `--crop smart` — use `--crop crop --smart` instead (still works, shows deprecation warning)
- `--crop smart_pad` — use `--crop pad --smart` instead (still works, shows deprecation warning)

### Fixed
- `team_level` in overlay context now uses the actual team level (e.g., "2016", "bantam") instead of the sport name — previously showed "hockey" instead of the level
- Segment merge and highlights merge output extension now matches input files instead of being hardcoded to `.mkv`
- Highlights merge now discovers segment files with any video extension (`.mp4`, `.mkv`, `.mov`, etc.), not just `.mkv`

## [0.0.32] - 2026-03-15

### Fixed
- `--profile` now resolves relative to the active config directory (parent of `REELN_CONFIG`) instead of the platform default, so profiles stored alongside a custom config file are found correctly
- `--profile` and `--path` CLI arguments now take strict priority over `REELN_CONFIG` and `REELN_PROFILE` environment variables

## [0.0.31] - 2026-03-13

### Added
- `ON_POST_GAME_FINISH` hook — fires after `ON_GAME_FINISH` with shared context, enabling cross-plugin data consumption at game finish (mirrors `ON_GAME_INIT` → `ON_GAME_READY` pattern)
- `--log-level` CLI option and `REELN_LOG_LEVEL` env var to control log verbosity (default: WARNING)
- `enforce_hooks` plugin config option — restricts plugins to hooks declared in the registry; set `false` for local plugin development
- Registry capability enforcement — plugins can only register hooks declared in their `registry/plugins.json` entry

### Fixed
- Explicit `--profile` or `--path` to a nonexistent config file now fails immediately instead of silently using defaults

### Changed
- Default log level changed from INFO to WARNING (reduces noise during normal operation)

## [0.0.30] - 2026-03-11

### Added
- `ON_GAME_READY` hook — fires after `ON_GAME_INIT` with shared context, enabling cross-plugin data consumption (e.g. OpenAI generates thumbnail during init, Google updates livestream during ready)
- `config show` now displays the full resolved configuration including all default values and plugin schema defaults
- Plugin registry entries for `meta` (Facebook Live/Instagram/Threads) and `openai` (LLM-powered metadata/thumbnails/translation)

### Fixed
- PyPI Documentation link now points to correct URL (`reeln-cli.readthedocs.io`)

### Changed
- Plugins that are not installed log at debug level instead of warning with traceback

## [0.0.29] - 2026-03-06

### Added
- `--version` / `-V` flag on `reeln plugins install` and `reeln plugins update` to pin a specific version (git tag or PyPI release)
- Logo on Read the Docs site (sidebar and favicon)

## [0.0.28] - 2026-03-04

### Added
- `--description` / `-d` flag on `game init` for broadcast description
- `--thumbnail` flag on `game init` for thumbnail image path
- `GameInfo.description` and `GameInfo.thumbnail` fields
- Interactive prompts for description and thumbnail (both optional)

## [0.0.27] - 2026-03-04

### Fixed
- PyPI logo: restore absolute URL for README image (lost during merge)

## [0.0.26] - 2026-03-04

### Added
- `HookContext.shared` dict for plugins to pass data back (e.g. livestream URLs)
- `GameState.livestreams` field — persists livestream URLs written by hook plugins
- `resolve_config_path()` — extracted config path resolution for reuse

### Fixed
- Plugin install now uses `git+{homepage}` for GitHub/GitLab plugins instead of PyPI lookup
- Post-install verification catches silent `uv pip install` no-ops
- `save_config()` now respects `REELN_CONFIG` / `REELN_PROFILE` env vars (previously always wrote to default path)
- `detect_installer()` passes `--python sys.executable` to uv so plugins install into the correct environment
- Hardcoded version strings removed from tests (use `__version__` dynamically)

## [0.0.25] - 2026-03-04

### Fixed
- Logo image on PyPI (use absolute URL for `assets/logo.jpg`)
- Add project URLs to PyPI sidebar (Homepage, Docs, Repo, Changelog, Issues)

## [0.0.24] - 2026-03-04

### Fixed
- Registry URL casing — `raw.githubusercontent.com` is case-sensitive (`StreamnDad` not `streamn-dad`)
- mypy errors in `prompts.py` (renamed shadowed variables)
- CI workflows use `uv sync` instead of `uv pip install --system` (PEP 668)
- Plugin registry: correct homepage URL and metadata for `streamn-scoreboard`

## [0.0.23] - 2026-03-03

First feature-complete release of reeln — platform-agnostic CLI toolkit for livestreamers.

### Added

#### CLI Commands
- `reeln --version` — show version, ffmpeg info, and installed plugin versions
- `reeln doctor` — comprehensive health check: ffmpeg, codecs, hardware acceleration, config, permissions
- `reeln config show` — display current configuration as JSON
- `reeln config doctor` — validate config, warn on issues
- `reeln game init` — initialize game workspace with sport-specific segment subdirectories
- `reeln game segment <N>` — merge replays in a segment directory into a highlight video
- `reeln game highlights` — merge all segment highlights into a full-game highlight reel
- `reeln game finish` — mark a game as finished with summary
- `reeln game prune` — remove generated artifacts from a finished game directory
- `reeln game event list` — list events with filters (`--segment`, `--type`, `--untagged`)
- `reeln game event tag` — tag an event with type, player, and metadata
- `reeln game event tag-all` — bulk-tag all events in a segment
- `reeln game compile` — compile raw event clips into a single video by criteria
- `reeln render short` — render a 9:16 short from a clip
- `reeln render preview` — fast low-res preview render
- `reeln render apply` — apply a named render profile to a clip (full-frame, no crop/scale)
- `reeln render reel` — assemble rendered shorts into a concatenated reel
- `reeln media prune` — scan and prune all finished game directories
- `reeln plugins list` — list installed plugins with version info
- `reeln plugins search` — search the plugin registry
- `reeln plugins info <name>` — show detailed plugin information
- `reeln plugins install <name>` — install a plugin from the registry with auto-enable
- `reeln plugins update [name]` — update a plugin or all installed plugins
- `reeln plugins enable <name>` / `reeln plugins disable <name>` — enable/disable plugins

#### Core Features
- Package skeleton: `pyproject.toml`, Makefile, `.coveragerc`, `pytest.ini`, `python -m reeln` support
- Structured logging module with JSON and human formatters
- Error hierarchy: `ReelnError` base with typed subclasses
- FFmpeg discovery with cross-platform support (PATH, brew, apt, choco), version checking (5.0+ minimum)
- Media probe helpers: duration, fps, resolution via ffprobe
- Deterministic ffmpeg command builders (concat, render) with golden test assertions
- `FFmpegRenderer` implementation with `render()` and `preview()` methods
- Config system: JSON loading, schema validation, `config_version`, XDG-compliant paths, env var overrides (`REELN_<SECTION>_<KEY>`), deep merge, atomic writes, named profiles
- Segment model: generic time division abstraction with sport alias registry (hockey, basketball, soccer, football, baseball, lacrosse, generic) and custom sport registration
- Game lifecycle: `GameInfo`, `GameState`, `GameEvent` models with JSON serialization, double-header auto-detection, `game.json` state tracking
- `GameEvent` model for first-class event tracking with UUID-based IDs, prefix matching, extensible metadata, and idempotent creation
- Render state tracking in `game.json` via `RenderEntry` with event auto-linking
- ShortConfig model with crop modes (pad, crop), output formats (vertical, square), anchor positions
- Filter graph builders: scale, pad, crop, speed, LUT, subtitle — composable and golden-tested
- Render profiles: named configuration sets for reusable rendering parameter overrides (speed, LUT, subtitle template, encoding)
- Multi-iteration rendering: run a clip through N render profiles sequentially and concatenate results
- Template engine: `{{key}}` placeholder substitution for `.ass` subtitle files
- `TemplateContext`, `TemplateProvider` protocol, `build_base_context()` for game/event context
- ASS subtitle helpers: `rgb_to_ass()`, `format_ass_time()`
- Bundled `goal_overlay` ASS subtitle template with dynamic font sizing and team-colored background
- `builtin:` prefix for `subtitle_template` in render profiles (e.g. `"builtin:goal_overlay"`)
- `build_overlay_context()` for computing overlay-specific template variables from event metadata
- `--player` and `--assists` CLI flags on `render short`, `render preview`, and `render apply` — populate overlay template variables without game event tagging; override event data when both are present
- Default `player-overlay` render profile and `goal` iteration mapping in bundled config
- `TeamProfile` model with metadata (logo, roster, colors, jersey colors, period length)
- Team profile management: load, save, list, delete with atomic writes
- Interactive team selection and game time prompting in `game init`
- `--game-time`, `--level`, `--period-length`, `--venue` options on `game init`
- `--debug` flag on game and render commands — writes pipeline debug artifacts with ffmpeg commands, filter chains, and metadata
- HTML debug index (`debug/index.html`) with summary table and per-operation sections
- `--dry-run` support across all destructive and render commands
- `PruneResult` model, `format_bytes()`, `find_game_dirs()` helpers
- `CompilationResult` model for compilation output tracking
- `questionary` as optional dependency (`pip install reeln[interactive]`)

#### Plugin System
- Plugin system foundation: lifecycle hooks, capability protocols, hook registry
- `Hook` enum with 11 lifecycle hooks: `PRE_RENDER`, `POST_RENDER`, `ON_CLIP_AVAILABLE`, `ON_EVENT_CREATED`, `ON_EVENT_TAGGED`, `ON_GAME_INIT`, `ON_GAME_FINISH`, `ON_HIGHLIGHTS_MERGED`, `ON_ERROR`, `ON_SEGMENT_START`, `ON_SEGMENT_COMPLETE`
- `HookRegistry` with safe emission — handler exceptions are caught and logged
- Capability protocols: `Uploader`, `MetadataEnricher`, `Notifier`, `Generator`
- Plugin orchestrator: sequential pipeline (Generator -> MetadataEnricher -> Uploader -> Notifier)
- Plugin loader: `discover_plugins()`, `load_plugin()`, `load_enabled_plugins()`, `activate_plugins()`
- Plugin config schema declaration with `ConfigField` and `PluginConfigSchema`
- Remote plugin registry with cache, search, install, update, and auto-enable
- `author` and `license` fields on plugin registry entries
- `ThrottledReader` for upload throughput limiting, `upload_lock()` for serialization
- `filelock>=3.0` dependency

#### CI/CD & Docs
- GitHub Actions CI workflow (Python 3.11/3.12/3.13 matrix, lint, type check, tests, docs build)
- GitHub Actions release workflow (tag-based PyPI publish via trusted publisher)
- CI and docs badges in README
- Documentation infrastructure: Sphinx + MyST, Furo theme, Read the Docs config
- Full docs site: install guide, quickstart tutorial, CLI reference, configuration guide, sports guide

### Fixed
- `render short --render-profile` now correctly resolves `subtitle_template` from the profile — previously the template was silently dropped in the single-profile path

### Changed
- `--rink` CLI flag renamed to `--venue` for sport-agnostic terminology
- Segment merge and highlights merge output written to `paths.output_dir` for discoverability
- `period_length` moved from `TeamProfile` to `GameInfo`
- Full test suite with 100% line + branch coverage
