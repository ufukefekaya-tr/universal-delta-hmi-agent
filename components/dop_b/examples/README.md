# Neutral pilot and synthetic fixtures

These original layouts describe conceptual design intent. They contain no customer identity, brand graphics, IP address, PLC endpoint or vendor-native project source. The `DEMO.*` addresses and `SIM/OFFLINE` channel/station are declared synthetic markers; they are not validated controller addresses.

| Design | Layout | Selected synthetic profile | Purpose |
| --- | --- | --- | --- |
| `neutral_800x480.json` | 800 × 480 | `synthetic_dopsoft2` | Model-independent neutral pilot |
| `neutral_1024x600.json` | 1024 × 600 | `synthetic_diascreen` | Model-independent neutral pilot |
| `synthetic_dopsoft2_design.json` | 800 × 480 | `synthetic_dopsoft2` | Original offline qualification intent; DOP-B07S411 target selection |
| `synthetic_diascreen_design.json` | 1024 × 600 | `synthetic_diascreen` | Original offline qualification intent; DOP-110IS target selection |

The named model targets select future qualification work; they do not assert device resolution, exact editor compatibility, driver acceptance or family support. Synthetic profiles and fixtures produce offline framework evidence only. Genuine vendor fixtures, editor compile/simulation results and panel acceptance are separate gates.

The run request and stop request are explicit writable BOOL commands. Their state labels describe requests. The run feedback reads a separate read-only BOOL tag. This prevents the drawing from treating a request bit as independent feedback; actual wiring and physical truth still require human evidence. Maintained requests define states 0 and 1. Speed input uses explicit 0–5000 limits and one fractional digit; display and input keep `rpm` in a separate unit field.

V1 rejects unknown IR properties and properties that have no semantics for their element kind. Numeric inputs read and write the same logical process tag with exact type/unit matching; V1 performs no implicit conversion. Boolean state 0/1 must differ in text or fill. Optional native screen/element aliases are canonical nonnegative integer strings. Tag `native_binding` requires exactly `link` and `mem_type`, each a nonnegative integer or canonical integer string within 0–2147483647. Integration metadata is explicit identity data, not vendor qualification.

`universal_hmi.preview.render_preview` emits standalone conceptual HTML. `values` maps tag IDs to numeric samples; `states` maps IDs to `valid`, `invalid` or `stale`. Example:

```python
samples = {
    "run_feedback": 1, "run_request": 0, "stop_request": 0,
    "actual_speed": 1420.5, "speed_setpoint": 1500.0, "alarm_active": 0,
}
html = render_preview(design, profile, values=samples, states={"run_feedback": "valid"})
```

External sample controls change illustrations. Panel buttons do not execute commands, macros, navigation or alarm retention. Missing, malformed, out-of-type/range, invalid and stale samples show gray `UNKNOWN`; they never become OFF or healthy. An alarm history object has no persisted sample history and remains unknown. Common-model validation issues remain visible and block production, even when a conceptual view can be drawn.

`neutral_*.preview.html` and `neutral_*.preview.png` are generated conceptual review artifacts. Their initial state uses the samples above. `neutral_800x480.unknown.preview.png` shows all sample quality forced to invalid. Browser smoke checks covered external 0/1, invalid, stale and missing values, a large numeric value, limits, inert panel illustrations, and no remote requests. They are neither native screenshots nor panel acceptance evidence.

The focused visual repair keeps conceptual/sample qualifiers outside the canvas. Command and feedback headings remain explicit; gray UNKNOWN retains its quality reason. Active alarms have an amber accent and count, inactive alarms remain neutral. Long alarm text wraps before shrinking and keeps at least 14px; a message that cannot fit produces a visible `INSUFFICIENT SPACE` report rather than becoming unreadable or silently clipping. The additional request-state indicator is retained only as an offline qualification example and labeled outside the canvas.

`review/` contains 1:1 HMI crops and standalone HTML for both resolutions with state 0, state 1, actual per-tag stale quality, long valid number/active alarm, and an intentionally oversized alarm that must report insufficient space. The browser report measures text ranges against padded content boxes and line bounds; it includes source and artifact hashes for independent reinspection.
