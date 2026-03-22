# reeln-core Migration Plan

> **Goal:** Extract a shared Rust core library (`reeln-core`) from `reeln-cli` that
> serves as the single source of truth for media processing, game state management,
> and sport-specific logic — consumed by the Python CLI, Tauri desktop app, and OBS
> plugin via their respective bindings.

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│                  reeln-core (Rust)                    │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ reeln-media   │  │ reeln-state  │  │ reeln-sport│ │
│  │               │  │              │  │            │ │
│  │ libav* probing│  │ Game state   │  │ Sport      │ │
│  │ Concat/merge  │  │ machine      │  │ registry   │ │
│  │ Filter chains │  │ JSON persist │  │ Segments   │ │
│  │ HW accel      │  │ File locking │  │ Validation │ │
│  │ Codec query   │  │ Event log    │  │            │ │
│  └──────────────┘  └──────────────┘  └────────────┘ │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ reeln-overlay │  │ reeln-config │  │reeln-plugin│ │
│  │               │  │              │  │            │ │
│  │ Template eng. │  │ XDG paths    │  │ Hook system│ │
│  │ 2D rasterizer │  │ Layered merge│  │ Capabilites│ │
│  │ Text shaping  │  │ Env overrides│  │ Registry   │ │
│  │ Image composit│  │ Validation   │  │ Lifecycle  │ │
│  └──────────────┘  └──────────────┘  └────────────┘ │
├──────────────────────────────────────────────────────┤
│                   Binding Layer                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ reeln-python  │  │ reeln-ffi    │  │ (Tauri)    │ │
│  │ PyO3/maturin  │  │ C ABI for    │  │ direct dep │ │
│  │ → reeln-cli   │  │ → OBS plugin │  │ → Tauri app│ │
│  └──────────────┘  └──────────────┘  └────────────┘ │
└──────────────────────────────────────────────────────┘
```

---

## 2. Repository Structure: `reeln-core`

```
reeln-core/
├── Cargo.toml                    # Workspace root
├── LICENSE                       # AGPL-3.0-only (match reeln-cli)
├── README.md
│
├── crates/
│   ├── reeln-media/              # Phase 1a — Media operations
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── probe.rs          # Duration, FPS, resolution via libav*
│   │       ├── concat.rs         # Stream-copy concat + re-encode concat
│   │       ├── render.rs         # General render pipeline (scale, codec, CRF)
│   │       ├── filter.rs         # Filter chain builder (crops, shorts, overlay compositing)
│   │       ├── codec.rs          # Codec/hwaccel discovery
│   │       └── error.rs          # MediaError types
│   │
│   ├── reeln-overlay/            # Phase 1b — Overlay template engine (replaces ASS)
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── template.rs       # Template model, JSON/TOML loading, registry
│   │       ├── elements.rs       # Primitives: Rect, Text, Image, Gradient
│   │       ├── layout.rs         # Percentage-based positioning, resolution scaling
│   │       ├── text.rs           # Font loading, text shaping, measurement, auto-shrink
│   │       ├── render.rs         # Rasterize template → RGBA frame(s) via tiny-skia
│   │       ├── animation.rs      # Timing, fade in/out, easing curves
│   │       └── error.rs          # OverlayError types
│   │
│   ├── reeln-sport/              # Phase 2 — Sport & segment logic
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── registry.rs       # Built-in + custom sport aliases
│   │       ├── segment.rs        # Segment creation, naming, validation
│   │       └── error.rs
│   │
│   ├── reeln-state/              # Phase 2 — Game state machine
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── game.rs           # GameInfo, GameEvent, GameState structs
│   │       ├── persist.rs        # JSON load/save with atomic writes
│   │       ├── directory.rs      # Game dir creation, double-header detection
│   │       ├── replay.rs         # Replay collection (file move)
│   │       └── error.rs
│   │
│   ├── reeln-config/             # Phase 3 — Configuration system
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── paths.rs          # XDG/platform config & data dirs
│   │       ├── model.rs          # AppConfig, VideoConfig, PathConfig structs
│   │       ├── loader.rs         # Load, merge, env overrides, validation
│   │       └── error.rs
│   │
│   ├── reeln-plugin/             # Phase 4 — Plugin system
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── hooks.rs          # Hook enum, HookContext, emission
│   │       ├── capabilities.rs   # Uploader, Notifier, Generator traits
│   │       ├── registry.rs       # Plugin discovery and activation
│   │       └── loader.rs         # Dynamic loading (dlopen/libloading)
│   │
│   ├── reeln-python/             # Phase 5 — Python bindings
│   │   ├── Cargo.toml            # depends on all reeln-* crates + pyo3
│   │   ├── pyproject.toml        # maturin build config
│   │   └── src/
│   │       ├── lib.rs            # #[pymodule] reeln_native
│   │       ├── media.rs          # probe_duration, concat_segments, etc.
│   │       ├── sport.rs          # get_sport, list_sports, etc.
│   │       ├── state.rs          # load/save game state
│   │       └── config.rs         # load/save config
│   │
│   ├── reeln-ffi/                # Phase 6 — C ABI for OBS plugin
│   │   ├── Cargo.toml
│   │   ├── include/
│   │   │   └── reeln.h           # Generated C header (cbindgen)
│   │   └── src/
│   │       └── lib.rs            # #[no_mangle] extern "C" exports
│   │
│   └── reeln-tauri/              # Phase 7 — Tauri desktop app
│       ├── Cargo.toml
│       ├── src-tauri/
│       │   ├── Cargo.toml        # depends on reeln-media, reeln-state, etc.
│       │   ├── src/
│       │   │   ├── main.rs
│       │   │   └── commands.rs   # Tauri IPC command handlers
│       │   └── tauri.conf.json
│       └── src/                  # Frontend (Svelte + TypeScript)
│           ├── App.svelte
│           ├── lib/
│           └── routes/
│
├── tests/                        # Integration tests across crates
│   ├── media_integration.rs
│   └── state_roundtrip.rs
│
└── .github/
    └── workflows/
        ├── ci.yml                # cargo test, clippy, fmt
        ├── python.yml            # maturin build + pytest
        └── release.yml           # Cross-compile + publish
```

---

## 3. Phased Migration

### Phase 1a: `reeln-media` — FFmpeg/libav* operations

**What moves from Python:**
| Python source | Rust target | Notes |
|---|---|---|
| `core/ffmpeg.py:discover_ffmpeg()` | Removed | No longer needed — libav* is linked in |
| `core/ffmpeg.py:probe_duration()` | `reeln-media/probe.rs` | Via `avformat_open_input` + `avformat_find_stream_info` |
| `core/ffmpeg.py:probe_fps()` | `reeln-media/probe.rs` | Read `avg_frame_rate` from stream info |
| `core/ffmpeg.py:probe_resolution()` | `reeln-media/probe.rs` | Read `width`/`height` from codec params |
| `core/ffmpeg.py:list_codecs()` | `reeln-media/codec.rs` | Iterate `avcodec_iterate()` |
| `core/ffmpeg.py:list_hwaccels()` | `reeln-media/codec.rs` | Query `av_hwdevice_iterate_types()` |
| `core/ffmpeg.py:build_concat_command()` | `reeln-media/concat.rs` | Direct muxer API, no subprocess |
| `core/ffmpeg.py:build_short_command()` | `reeln-media/filter.rs` | `avfilter_graph` API |
| `core/ffmpeg.py:build_render_command()` | `reeln-media/render.rs` | Encode pipeline via `avcodec` |
| `core/ffmpeg.py:run_ffmpeg()` | Removed | No subprocess — all in-process |
| `core/renderer.py:Renderer` | `reeln-media/render.rs` | `trait Renderer` |
| `core/renderer.py:FFmpegRenderer` | `reeln-media/render.rs` | `struct LibavRenderer` |

**Key Rust dependencies:**
- `ffmpeg-next` — Safe Rust bindings to libavcodec/libavformat/libavfilter/libswscale
- `thiserror` — Error types

**Trait design:**
```rust
// reeln-media/src/lib.rs

pub trait MediaBackend: Send + Sync {
    fn probe(&self, path: &Path) -> Result<MediaInfo, MediaError>;
    fn concat(&self, segments: &[&Path], output: &Path, opts: ConcatOptions) -> Result<(), MediaError>;
    fn render(&self, plan: &RenderPlan) -> Result<RenderResult, MediaError>;
}

pub struct MediaInfo {
    pub duration_secs: Option<f64>,
    pub fps: Option<f64>,
    pub width: Option<u32>,
    pub height: Option<u32>,
    pub codec: Option<String>,
}

pub struct ConcatOptions {
    pub copy: bool,              // stream copy vs re-encode
    pub video_codec: String,     // e.g. "libx264"
    pub crf: u32,
    pub audio_codec: String,
    pub audio_rate: u32,
}
```

**Deliverable:** `cargo test` passes for probe, concat, and render operations against sample media files. Python CLI continues working unchanged (Rust not wired in yet).

---

### Phase 1b: `reeln-overlay` — Template rendering engine (replaces ASS)

**Why:** The current ASS subtitle overlay system (`goal_overlay.ass`) requires `ffmpeg-full`
built with `--enable-libass --enable-libfontconfig --enable-libfreetype --enable-libfribidi`.
It is also limited to hard-coded 1920x1080 pixel coordinates, cannot embed images (team logos),
and has no support for gradients, rounded corners, or animations beyond simple timing.

The `reeln-overlay` crate replaces ASS with a **native Rust 2D rendering engine** that
rasterizes overlay templates to RGBA image frames. These frames are composited onto video
using libav*'s built-in `overlay` filter — available in **every** FFmpeg/libav* build
with zero additional dependencies.

**What moves from Python:**
| Python source | Rust target | Notes |
|---|---|---|
| `core/overlay.py:resolve_builtin_template()` | `reeln-overlay/template.rs` | Template registry with builtin + user + plugin templates |
| `core/overlay.py:overlay_font_size()` | `reeln-overlay/text.rs` | Replaced by `auto_shrink` in text element spec |
| `core/overlay.py:build_overlay_context()` | `reeln-overlay/render.rs` | Context variables resolved during rasterization |
| `core/overlay.py:_parse_assists()` | `reeln-overlay/template.rs` | Template conditionals (`visible` field) handle this |
| `core/overlay.py:_parse_color()` | `reeln-overlay/elements.rs` | Native `Color` type with hex/rgb/named parsing |
| `core/templates.py:render_template()` | `reeln-overlay/template.rs` | `{{var}}` substitution + conditionals |
| `core/templates.py:render_template_file()` | `reeln-overlay/template.rs` | Loads JSON/TOML templates (replaces .ass files) |
| `core/templates.py:build_base_context()` | `reeln-overlay/template.rs` | Context builder from game info + events |
| `core/templates.py:rgb_to_ass()` | Removed | No longer needed — colors are native RGBA |
| `core/templates.py:format_ass_time()` | Removed | Timing is in the template's `timing` block |
| `core/templates.py:TemplateProvider` | `reeln-overlay/template.rs` | `trait TemplateProvider` (plugins contribute variables) |
| `core/shorts.py:build_subtitle_filter()` | `reeln-media/filter.rs` | Replaced by `overlay` filter compositing PNG frames |
| `data/templates/goal_overlay.ass` | `data/templates/goal_overlay.json` | Migrated to JSON template format (see below) |

**Key Rust dependencies:**
- `tiny-skia` — CPU 2D rasterizer (rects, rounded rects, paths, gradients, image compositing)
- `cosmic-text` — Font discovery, loading, shaping, measurement, line wrapping (Unicode, ligatures, RTL)
- `image` — PNG encode/decode for rendered overlay frames

**Element primitives:**
```rust
// reeln-overlay/src/elements.rs

/// A visual element within an overlay template.
pub enum Element {
    Rect {
        bounds: Bounds,                 // x, y, w, h — percentage (0.0-1.0) or pixels
        fill: Color,
        corner_radius: f32,
        border: Option<Border>,
        opacity: f32,
    },
    Text {
        content: String,                // supports {{var}} placeholders
        position: Position,
        font: FontSpec,                 // family, size, weight, auto_shrink min size
        color: Color,
        outline: Option<OutlineSpec>,
        alignment: Alignment,
        max_width: Option<f32>,
        visible: Option<String>,        // conditional: "{{has_assists}}"
    },
    Image {
        source: ImageSource,            // file path, embedded bytes, or {{var}} path
        position: Position,
        size: Size,
        fit: ImageFit,                  // contain, cover, fill
        opacity: f32,
    },
    Gradient {
        bounds: Bounds,
        stops: Vec<GradientStop>,       // color + position pairs
        direction: GradientDirection,   // horizontal, vertical, angle(f32)
        corner_radius: f32,
    },
}

pub enum ImageSource {
    File(PathBuf),                      // e.g. team logo on disk
    Embedded(Vec<u8>),                  // logo stored in game state / team profile
    Variable(String),                   // "{{team_logo}}" — resolved at render time
}
```

**Template format (JSON, replaces ASS):**
```json
{
  "name": "goal-overlay",
  "version": 2,
  "canvas": { "width": 1920, "height": 1080 },
  "layers": [
    {
      "type": "rect",
      "x": "0%", "y": "76%", "w": "100%", "h": "13%",
      "fill": "{{primary_color}}",
      "opacity": 0.9
    },
    {
      "type": "rect",
      "x": "0.15%", "y": "76.3%", "w": "99.7%", "h": "12.5%",
      "fill": "{{primary_color}}",
      "opacity": 0.6
    },
    {
      "type": "image",
      "source": "{{team_logo}}",
      "x": "1%", "y": "77%", "w": "4%", "h": "auto",
      "fit": "contain"
    },
    {
      "type": "text",
      "content": "{{team_name}}  -  {{sport}}",
      "x": "6%", "y": "77.5%",
      "font": { "family": "Inter", "size": 22, "weight": "normal" },
      "color": "{{text_color}}"
    },
    {
      "type": "text",
      "content": "{{scorer}}",
      "x": "6%", "y": "80%",
      "font": { "family": "Inter", "size": 46, "weight": "bold", "auto_shrink": 32 },
      "color": "#FFFFFF"
    },
    {
      "type": "text",
      "content": "{{assist_1}}",
      "x": "7.5%", "y": "84%",
      "font": { "family": "Inter", "size": 24, "auto_shrink": 18 },
      "color": "#FFFFFF",
      "visible": "{{has_assists}}"
    },
    {
      "type": "text",
      "content": "{{assist_2}}",
      "x": "7.5%", "y": "86%",
      "font": { "family": "Inter", "size": 24, "auto_shrink": 18 },
      "color": "#FFFFFF",
      "visible": "{{has_assists_2}}"
    }
  ],
  "timing": {
    "fade_in": 0.3,
    "hold": 10.0,
    "fade_out": 0.5
  }
}
```

**Key improvements over ASS:**
| Capability | ASS (current) | reeln-overlay (new) |
|---|---|---|
| Positioning | Absolute pixels (1920x1080 only) | Percentage-based (any resolution) |
| Team logos | Not possible | `Image` element with `contain`/`cover` fit |
| Rounded corners | Not possible | `corner_radius` on Rect/Gradient |
| Gradients | Not possible | Linear/radial with arbitrary stops |
| Auto-shrink text | Manual `overlay_font_size()` hack | Built-in `auto_shrink` min size on font spec |
| Conditional visibility | Zero-duration timing hack | `visible: "{{has_assists}}"` field |
| Animations | Start/end time only | Fade in/out with easing curves |
| Colors | BGR `&HAABBGGRR` format | Standard hex `#RRGGBB` / `rgba()` / named |
| Template format | ASS subtitle markup + `\p1` drawing hacks | Clean JSON/TOML with typed elements |
| FFmpeg requirement | `ffmpeg-full` (libass, libfontconfig, libfreetype, libfribidi) | **Standard ffmpeg** (`overlay` filter is always built in) |
| User-editable | Requires ASS knowledge | JSON — editable by anyone |
| Live preview | Not possible | Rasterize to PNG — previewable in Tauri app |
| Plugin templates | `TemplateProvider` returns string vars | `TemplateProvider` returns structured elements |

**Rendering pipeline — how it replaces ASS:**
```
BEFORE (ASS — requires ffmpeg-full):
  Template vars → substitute into .ass file → ffmpeg -vf "ass='overlay.ass'" → output
  Dependencies: libass, libfontconfig, libfreetype, libfribidi, harfbuzz

AFTER (reeln-overlay — standard ffmpeg):
  Template JSON + context vars
       │
       ▼
  reeln-overlay rasterizes → RGBA PNG frame(s)
       │                      (tiny-skia + cosmic-text)
       ▼
  reeln-media composites via libav* overlay filter → output
       │                      (built into every ffmpeg)
       ▼
  Final video with overlay burned in
```

**Two compositing strategies (start with A, evolve to B):**

*Strategy A — PNG overlay (Phase 1b):*
```rust
// Render template to PNG, composite via overlay filter
pub fn apply_overlay(
    video: &Path,
    template: &Template,
    context: &TemplateContext,
    output: &Path,
    timing: &Timing,
) -> Result<(), OverlayError> {
    let frame = render_template_to_png(template, context)?;
    // Uses libav* overlay filter: [1:v]fade=in:...[ov];[0:v][ov]overlay=0:0
    reeln_media::composite_overlay(video, &frame, output, timing)?;
    Ok(())
}
```

*Strategy B — Direct frame injection (future optimization):*
```rust
// Decode frame → blend overlay RGBA onto decoded frame → encode
// No temp files, fully in-process via libav* APIs
pub fn render_with_overlay(
    input: &Path,
    template: &Template,
    context: &TemplateContext,
    output: &Path,
) -> Result<(), OverlayError> {
    // Per-frame: decode → composite RGBA overlay → encode
    // Supports per-frame animation (slide in, fade, etc.)
}
```

**Deliverable:** A goal overlay template renders to PNG with team name, scorer, assists, team colors, and team logo. The PNG composites onto a test video using the `overlay` filter. Visual output matches the current ASS overlay.

---

### Phase 2: `reeln-sport` + `reeln-state` — Domain logic

**What moves from Python:**
| Python source | Rust target |
|---|---|
| `core/segment.py` (entire module) | `reeln-sport/` |
| `models/segment.py` (Segment, SportAlias) | `reeln-sport/segment.rs` |
| `core/highlights.py:game_dir_name()` | `reeln-state/directory.rs` |
| `core/highlights.py:detect_next_game_number()` | `reeln-state/directory.rs` |
| `core/highlights.py:create_game_directory()` | `reeln-state/directory.rs` |
| `core/highlights.py:load_game_state()` | `reeln-state/persist.rs` |
| `core/highlights.py:save_game_state()` | `reeln-state/persist.rs` |
| `core/highlights.py:find_segment_videos()` | `reeln-state/directory.rs` |
| `core/highlights.py:collect_replays()` | `reeln-state/replay.rs` |
| `models/game.py` (all structs + serde) | `reeln-state/game.rs` |

**Key Rust dependencies:**
- `serde` + `serde_json` — Replaces hand-written dict serialization
- `chrono` — Timestamps (replaces `datetime`)
- `uuid` — Event IDs
- `fs2` or `fd-lock` — File locking (replaces `filelock`)

**Struct design (serde replaces manual serialization):**
```rust
// reeln-state/src/game.rs
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameInfo {
    pub date: String,
    pub home_team: String,
    pub away_team: String,
    pub sport: String,
    #[serde(default = "default_game_number")]
    pub game_number: u32,
    #[serde(default)]
    pub venue: String,
    // ...
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameState {
    pub game_info: GameInfo,
    #[serde(default)]
    pub segments_processed: Vec<u32>,
    #[serde(default)]
    pub highlighted: bool,
    #[serde(default)]
    pub finished: bool,
    #[serde(default)]
    pub events: Vec<GameEvent>,
    #[serde(default)]
    pub renders: Vec<RenderEntry>,
    #[serde(default)]
    pub livestreams: HashMap<String, String>,
    // ...
}
```

**Deliverable:** Full round-trip test: create game dir → write state → read state → validate. `game.json` format identical to Python version (backward compatible).

---

### Phase 3: `reeln-config` — Configuration system

**What moves from Python:**
| Python source | Rust target |
|---|---|
| `core/config.py:config_dir()`, `data_dir()` | `reeln-config/paths.rs` |
| `core/config.py:load_config()`, `save_config()` | `reeln-config/loader.rs` |
| `core/config.py:deep_merge()` | `reeln-config/loader.rs` |
| `core/config.py:apply_env_overrides()` | `reeln-config/loader.rs` |
| `core/config.py:validate_config()` | `reeln-config/loader.rs` |
| `models/config.py` (all dataclasses) | `reeln-config/model.rs` |

**Key Rust dependencies:**
- `dirs` — XDG/platform directory resolution
- `serde` + `serde_json` — Config serialization

**Deliverable:** Config loads identically to Python. Same JSON format, same env var prefixes (`REELN_*`), same merge semantics.

---

### Phase 4: `reeln-plugin` — Plugin system

**What moves from Python:**
| Python source | Rust target |
|---|---|
| `plugins/hooks.py` | `reeln-plugin/hooks.rs` |
| `plugins/capabilities.py` | `reeln-plugin/capabilities.rs` |
| `plugins/registry.py` | `reeln-plugin/registry.rs` |
| `plugins/loader.py` | `reeln-plugin/loader.rs` |

**Key design decision:** Plugins in Rust use `libloading` for dynamic `.so`/`.dll`/`.dylib` loading, or a trait-based static plugin system. Both Python plugins (via PyO3 callback) and native Rust plugins should be supported.

**Deliverable:** Hook emission works. A test plugin can register and receive `ON_GAME_INIT` events.

---

### Phase 5: `reeln-python` — Wire into reeln-cli

**Approach:** Use [PyO3](https://pyo3.rs) + [maturin](https://maturin.rs) to build a Python native extension module `reeln_native`.

```rust
// reeln-python/src/lib.rs
use pyo3::prelude::*;

#[pyfunction]
fn probe_duration(path: &str) -> PyResult<Option<f64>> {
    let info = reeln_media::probe(Path::new(path))
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
    Ok(info.duration_secs)
}

#[pyfunction]
fn concat_segments(paths: Vec<String>, output: &str, copy: bool) -> PyResult<()> {
    // ...
}

#[pymodule]
fn reeln_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(probe_duration, m)?)?;
    m.add_function(wrap_pyfunction!(concat_segments, m)?)?;
    // ...
    Ok(())
}
```

**Migration in `reeln-cli`:**
```python
# reeln/core/ffmpeg.py — Phase 5 swap
try:
    from reeln_native import probe_duration as _native_probe
    _USE_NATIVE = True
except ImportError:
    _USE_NATIVE = False

def probe_duration(ffmpeg_path: Path, input_path: Path) -> float | None:
    if _USE_NATIVE:
        return _native_probe(str(input_path))
    # ... existing subprocess fallback ...
```

**Build integration:**
```toml
# reeln-cli/pyproject.toml additions
[project.optional-dependencies]
native = ["reeln-native"]  # pip install reeln[native]
```

**Deliverable:** `pip install reeln[native]` uses Rust for all media operations. `pip install reeln` still works with subprocess fallback. All existing tests pass against both backends.

---

### Phase 6: `reeln-ffi` — C ABI for OBS plugin

```rust
// reeln-ffi/src/lib.rs
use std::ffi::{CStr, c_char, c_int};

#[no_mangle]
pub extern "C" fn reeln_probe_duration(path: *const c_char, out_duration: *mut f64) -> c_int {
    let path_str = unsafe { CStr::from_ptr(path) }.to_str().unwrap_or("");
    match reeln_media::probe(Path::new(path_str)) {
        Ok(info) => {
            if let Some(dur) = info.duration_secs {
                unsafe { *out_duration = dur; }
                0  // success
            } else {
                -1  // no duration
            }
        }
        Err(_) => -2  // error
    }
}

#[no_mangle]
pub extern "C" fn reeln_create_game(
    base_dir: *const c_char,
    sport: *const c_char,
    home: *const c_char,
    away: *const c_char,
    date: *const c_char,
) -> c_int { ... }
```

**Header generation:** Use `cbindgen` to auto-generate `reeln.h` from the Rust source.

**OBS plugin links:** `-lreeln_ffi` in the OBS plugin's CMakeLists.txt.

**Deliverable:** A minimal OBS plugin (C++) can call `reeln_probe_duration()` and `reeln_create_game()` successfully.

---

### Phase 7: `reeln-tauri` — Desktop app

**Stack:** Tauri v2 + Svelte 5 + TypeScript

**Tauri commands (IPC):**
```rust
// src-tauri/src/commands.rs
#[tauri::command]
fn init_game(sport: &str, home: &str, away: &str, date: &str) -> Result<String, String> {
    // calls reeln_state + reeln_sport directly
}

#[tauri::command]
fn process_segment(game_dir: &str, segment: u32) -> Result<SegmentResult, String> {
    // calls reeln_media + reeln_state
}

#[tauri::command]
fn get_game_state(game_dir: &str) -> Result<GameState, String> {
    // calls reeln_state::load_game_state
}
```

**Frontend pages:**
- **Dashboard** — Active games, recent highlights
- **Game View** — Segment timeline, drag-and-drop clip reordering
- **Render Queue** — Progress bars, render history
- **Settings** — Config editor, plugin manager
- **Sport Profiles** — Custom sport definitions

**Deliverable:** Working Tauri app that can init a game, process segments, and merge highlights — all powered by the same Rust crates the CLI uses.

---

## 4. Key Dependencies by Crate

| Crate | Rust Dependencies |
|---|---|
| `reeln-media` | `ffmpeg-next`, `thiserror`, `log` |
| `reeln-overlay` | `reeln-media`, `tiny-skia`, `cosmic-text`, `image`, `serde`, `serde_json`, `thiserror` |
| `reeln-sport` | `serde`, `thiserror` |
| `reeln-state` | `reeln-sport`, `serde`, `serde_json`, `chrono`, `uuid`, `tempfile`, `thiserror` |
| `reeln-config` | `reeln-state`, `serde`, `serde_json`, `dirs`, `thiserror` |
| `reeln-plugin` | `reeln-state`, `libloading`, `thiserror` |
| `reeln-python` | All `reeln-*` crates, `pyo3` |
| `reeln-ffi` | All `reeln-*` crates, `cbindgen` (build) |
| `reeln-tauri` | All `reeln-*` crates, `tauri` |

---

## 5. What Stays in Python (reeln-cli)

The Python CLI remains the user-facing layer. These stay:

| Module | Reason |
|---|---|
| `cli.py` | Typer app, CLI argument parsing |
| `commands/*.py` | CLI command handlers (call into Rust via `reeln_native`) |
| `core/prompts.py` | Interactive prompts (questionary — terminal UI) |
| `core/log.py` | Python logging formatters |
| `core/doctor.py` | Health checks (adapted to verify native module) |

Everything in `core/` that does real work (ffmpeg, highlights, config, segment, renderer, overlay, templates, shorts) gets **replaced by thin wrappers** around `reeln_native` calls.

The ASS subtitle files (`data/templates/*.ass`) are replaced by JSON overlay templates
consumed by `reeln-overlay`. The `core/overlay.py`, `core/templates.py`, and ASS-related
code in `core/shorts.py` are fully superseded.

---

## 6. Backward Compatibility

- **`game.json` format** — Identical. Rust uses `serde` with the same field names and structure.
- **`config.json` format** — Identical. Same keys, same env var overrides.
- **`pip install reeln`** — Still works without Rust. Subprocess fallback remains.
- **`pip install reeln[native]`** — Installs Rust-powered backend. Faster, no FFmpeg binary needed.
- **Plugin API** — Python plugins continue to work. Rust plugins are an additional option.

---

## 7. CI/CD

```yaml
# .github/workflows/ci.yml
jobs:
  rust:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    steps:
      - cargo fmt --check
      - cargo clippy -- -D warnings
      - cargo test

  python:
    needs: rust
    steps:
      - maturin build --release
      - pip install dist/*.whl
      - pytest  # runs existing reeln-cli tests against native backend

  cross-compile:
    steps:
      - cross build --target x86_64-unknown-linux-gnu
      - cross build --target x86_64-apple-darwin
      - cross build --target aarch64-apple-darwin
      - cross build --target x86_64-pc-windows-msvc
```

---

## 8. Migration Timeline (Suggested Order)

| Phase | Crate | Depends On | What It Unlocks |
|---|---|---|---|
| **1a** | `reeln-media` | — | Eliminates FFmpeg binary dependency |
| **1b** | `reeln-overlay` | `reeln-media` | Eliminates ffmpeg-full/libass dependency; team logos, gradients, responsive overlays |
| **2** | `reeln-sport` + `reeln-state` | — | Shared domain logic |
| **3** | `reeln-config` | `reeln-state` | Shared configuration |
| **4** | `reeln-plugin` | `reeln-state` | Rust-native plugins |
| **5** | `reeln-python` | Phases 1-4 | Python CLI uses Rust backend |
| **6** | `reeln-ffi` | Phases 1-4 | OBS plugin can link reeln-core |
| **7** | `reeln-tauri` | Phases 1-4 | Desktop app (with live overlay preview) |

Phases 1a → 1b are sequential (overlay depends on media). Phase 2 can start in parallel
with Phase 1b. Phases 5, 6, and 7 can run in parallel once 1-4 are done.

---

## 9. Getting Started

```bash
# Create the new repository
mkdir reeln-core && cd reeln-core
cargo init --lib

# Set up workspace
cat > Cargo.toml << 'EOF'
[workspace]
resolver = "2"
members = [
    "crates/reeln-media",
    "crates/reeln-overlay",
    "crates/reeln-sport",
    "crates/reeln-state",
    "crates/reeln-config",
    "crates/reeln-plugin",
    "crates/reeln-python",
    "crates/reeln-ffi",
]

[workspace.dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
thiserror = "2"
log = "0.4"
ffmpeg-next = "7"
tiny-skia = "0.11"
cosmic-text = "0.12"
image = { version = "0.25", default-features = false, features = ["png"] }
uuid = { version = "1", features = ["v4"] }
chrono = { version = "0.4", features = ["serde"] }
tempfile = "3"
dirs = "6"
pyo3 = { version = "0.23", features = ["extension-module"] }
libloading = "0.8"
EOF

# Start with Phase 1a
mkdir -p crates/reeln-media/src
# ... begin porting ffmpeg.py → probe.rs, concat.rs, etc.

# Then Phase 1b
mkdir -p crates/reeln-overlay/src
# ... port overlay.py + templates.py → template.rs, elements.rs, render.rs, etc.
```
