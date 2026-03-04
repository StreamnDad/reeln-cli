# Sports and segments

reeln uses a generic segment model that adapts to any sport. Each sport defines a segment name, expected count, and optional default duration.

## Built-in sports

| Sport | Segment name | Count | Duration (min) | Directory example |
|---|---|---|---|---|
| hockey | period | 3 | 20 | `period-1/`, `period-2/`, `period-3/` |
| basketball | quarter | 4 | 12 | `quarter-1/` through `quarter-4/` |
| soccer | half | 2 | 45 | `half-1/`, `half-2/` |
| football | half | 2 | 30 | `half-1/`, `half-2/` |
| baseball | inning | 9 | -- | `inning-1/` through `inning-9/` |
| lacrosse | quarter | 4 | 12 | `quarter-1/` through `quarter-4/` |
| generic | segment | 1 | -- | `segment-1/` |

## How segments work

- All internal APIs use `segment_number: int` (1-indexed)
- The CLI accepts sport-specific terms: `reeln game segment 2` processes the 2nd segment (period, quarter, half, etc.)
- Directory structure uses the sport's segment name: `period-1/`, `quarter-1/`, `half-1/`
- Segment count is a hint for validation — reeln warns if you exceed it but doesn't block

## Custom sports

You can register custom sports in your config file under the `sports` key:

```json
{
  "config_version": 1,
  "sport": "rugby",
  "sports": [
    {
      "sport": "rugby",
      "segment_name": "half",
      "segment_count": 2,
      "duration_minutes": 40
    }
  ]
}
```

Custom sport fields:

| Field | Type | Description |
|---|---|---|
| `sport` | string | Sport name (used in `--sport` flag) |
| `segment_name` | string | What each segment is called |
| `segment_count` | integer | Expected number of segments |
| `duration_minutes` | integer or null | Default segment duration (null for variable) |

Custom sports override built-in entries if the name matches.
