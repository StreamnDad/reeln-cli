# reeln doctor

Run comprehensive health checks for your reeln environment.

## Usage

```bash
reeln doctor [OPTIONS]
```

## Description

`reeln doctor` performs a series of diagnostic checks and reports the status of each. It checks:

- **ffmpeg** — binary discovery and version (5.0+ required)
- **Codecs** — availability of key encoding codecs (libx264, libx265, aac)
- **Hardware acceleration** — available hardware acceleration methods (videotoolbox, cuda, etc.)
- **Configuration** — config file validity and schema version
- **Directories** — configured paths exist and are writable

Each check reports one of three statuses:

| Status | Meaning |
|---|---|
| PASS | Check passed successfully |
| WARN | Non-critical issue detected (hint provided) |
| FAIL | Critical issue that may prevent operation |

The command exits with code 0 if no FAIL results exist, or code 1 if any check failed.

## Options

| Option | Description |
|---|---|
| `--profile TEXT` | Named config profile to check |
| `--config PATH` | Explicit config file path to check |
| `--help` | Show help and exit |

## Examples

```bash
# Run all health checks
reeln doctor

# Check against a specific profile
reeln doctor --profile hockey

# Check with an explicit config file
reeln doctor --config /path/to/config.json
```

## Example output

```
  PASS: ffmpeg 7.1 at /opt/homebrew/bin/ffmpeg
  PASS: libx264 available
  PASS: libx265 available
  PASS: aac available
  PASS: Hardware acceleration: videotoolbox
  PASS: Configuration is valid
```

## Plugin extension

The doctor system supports plugin-contributed checks via the `DoctorCheck` protocol. Plugins can register additional health checks that run alongside the built-in checks:

```python
from reeln.models.doctor import CheckResult, CheckStatus, DoctorCheck

class MyPluginCheck:
    name = "my_plugin"

    def run(self) -> list[CheckResult]:
        return [
            CheckResult(
                name="my_plugin",
                status=CheckStatus.PASS,
                message="Plugin is healthy",
            )
        ]
```

## See also

- {doc}`config` — `config doctor` for config-only validation
- {doc}`/quickstart` — getting started guide
