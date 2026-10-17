"""Standalone conceptual preview. It contains no controller command transport."""

import html
import json
import math
import re

from .errors import HmiError
from .validation import COLORS, KINDS, NUMERIC, validate_design
from .value_model import FIXED_MODEL, raw_to_display


def _safe_json(value):
    try:
        # JSON in a script element still needs HTML-delimiter protection.
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise HmiError("INVALID_PREVIEW_DATA", "Preview data must be finite JSON data") from exc
    return serialized.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _text(value):
    return html.escape(str(value), quote=True)


def _int(value, default, minimum=0, maximum=16384):
    return value if isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum else default


def _color(value, default):
    return value if isinstance(value, str) and COLORS.fullmatch(value) else default


def _sample(tag_id, tag_map, values, states, valid):
    tag = tag_map.get(tag_id) if isinstance(tag_id, str) else None
    value = values.get(tag_id) if isinstance(tag_id, str) else None
    quality = states.get(tag_id, "valid") if isinstance(tag_id, str) else "invalid"
    if not valid or not tag or quality != "valid" or isinstance(value, bool) or not isinstance(value, (int, float)):
        return False, None, "STALE" if quality == "stale" else "INVALID / MISSING"
    if isinstance(value, float) and not math.isfinite(value):
        return False, None, "INVALID / MISSING"
    dtype = tag.get("data_type")
    if dtype == "BOOL":
        return isinstance(value, int) and value in (0, 1), value, "INVALID BOOL"
    limits = NUMERIC.get(dtype) if isinstance(dtype, str) else None
    if not limits or not limits[0] <= value <= limits[1] or (limits[2] == 0 and not isinstance(value, int)):
        return False, None, "TYPE / RANGE"
    return True, value, "VALUE"


def _initial_state(element, tag_map, values, states, valid):
    kind = element.get("kind")
    binding = element.get("binding", {})
    binding = binding if isinstance(binding, dict) else {}
    if kind == "numeric_input":
        read_id, write_id = binding.get("read"), binding.get("write")
        read_tag = tag_map.get(read_id) if isinstance(read_id, str) else None
        write_tag = tag_map.get(write_id) if isinstance(write_id, str) else None
        if not read_tag or not write_tag or read_id != write_id or read_tag.get("data_type") != write_tag.get("data_type") or read_tag.get("unit", "") != write_tag.get("unit", "") or write_tag.get("access") != "ReadWrite":
            return "UNKNOWN", "INPUT BINDING INVALID", "#303d4e", True
    ok, value, reason = _sample(binding.get("read"), tag_map, values, states, valid)
    if not ok:
        return "UNKNOWN", reason, "#303d4e", True
    if kind in ("button", "indicator"):
        state_list = element.get("states", [])
        state_list = state_list if isinstance(state_list, list) else []
        state = next((state for state in state_list if isinstance(state, dict) and state.get("value") == value), None)
        if not state or not isinstance(state.get("text"), str):
            return "UNKNOWN", "STATE UNDEFINED", "#303d4e", True
        return state["text"], "", _color(state.get("fill"), "#303d4e"), False
    for key, failed in (("minimum", lambda limit: value < limit), ("maximum", lambda limit: value > limit)):
        limit = element.get(key)
        if isinstance(limit, (int, float)) and not isinstance(limit, bool) and failed(limit):
            return "UNKNOWN", "ELEMENT RANGE", "#303d4e", True
    digits = _int(element.get("fractional"), 0, 0, 15)
    if element.get("value_model") == FIXED_MODEL:
        try:
            rendered = raw_to_display(value, tag_map[binding["read"]]["data_type"], digits)
        except (HmiError, KeyError):
            return "UNKNOWN", "VALUE MODEL INVALID", "#303d4e", True
    else:
        rendered = str(value) if abs(value) >= 1e21 else format(value, f".{digits}f")
    return rendered, "", _color(element.get("fill"), "#1b293b"), False


def _initial_alarm(element, alarms, tag_map, values, states, valid, invalid_view=False):
    if "view_policy" in element:
        if invalid_view or element["view_policy"] != "preserve_source":
            return "ALARM VIEW POLICY INVALID", "UNKNOWN", "NATIVE VIEW NOT RENDERED", "unknown source-preserved"
        note = "NO HISTORY DATA" if element.get("kind") == "alarm_history" else "NATIVE VIEW NOT RENDERED"
        return "SOURCE-PRESERVED PRESENTATION", "UNKNOWN", note, "unknown source-preserved"
    title = element.get("text", "ALARMS")
    if element.get("kind") == "alarm_history":
        return title, "UNKNOWN", "NO HISTORY DATA", "unknown"
    alarms = alarms if isinstance(alarms, list) else []
    samples = []
    for alarm in alarms:
        if not isinstance(alarm, dict):
            return title, "UNKNOWN", "ALARM BINDING INVALID", "unknown"
        tag_id = alarm.get("tag")
        tag = tag_map.get(tag_id) if isinstance(tag_id, str) else None
        if not tag or tag.get("data_type") != "BOOL":
            return title, "UNKNOWN", "ALARM BINDING INVALID", "unknown"
        samples.append((alarm, _sample(tag_id, tag_map, values, states, valid)))
    if not samples or any(not sample[0] for _, sample in samples):
        reason = "STALE" if any(sample[2] == "STALE" for _, sample in samples) else "ALARM DATA UNKNOWN"
        return title, "UNKNOWN", reason, "unknown"
    active = [alarm for alarm, sample in samples if sample[1] == 1]
    if active:
        return f"ACTIVE ALARMS · {len(active)}", " · ".join(str(a.get("text", "")) for a in active), "", "active"
    return "ALARMS · 0 ACTIVE", "No active alarms", "", ""


def render_preview(design, profile, values=None, states=None, valid=True, *, background_images=None):
    """Render escaped, offline HTML with sample controls outside the HMI canvas.

    ``values`` maps exact tag IDs to numeric sample values. ``states`` maps tag
    IDs to valid/invalid/stale quality. Missing and unrecognized values become
    UNKNOWN, never the OFF or healthy state. ``valid=False`` forces UNKNOWN.
    Sample changes illustrate state rendering only; no macro is executed and
    no element writes any real or simulated command tag. Source-pinned
    entry permission is not rendered, executed or simulated here; supplied
    values cannot enable its UNKNOWN placeholder.
    """
    if not isinstance(design, dict) or not isinstance(profile, dict):
        raise HmiError("INVALID_PREVIEW_DOCUMENT", "Design and profile must be objects")
    if values is not None and not isinstance(values, dict) or states is not None and not isinstance(states, dict):
        raise HmiError("INVALID_PREVIEW_DATA", "Sample values and states must be objects")
    schema = profile.get("native_schema")
    native_candidate_requested = isinstance(schema, dict) and "native_candidate" in schema
    candidate_spec = schema.get("native_candidate") if isinstance(schema, dict) else None
    edit_requested = isinstance(candidate_spec, dict) and candidate_spec.get("mode") == "existing_edit"
    issues = validate_design(design, profile)
    screens = design.get("screens", [])
    screens = [s for s in screens if isinstance(s, dict)] if isinstance(screens, list) else []
    requested = [s.get("native_id") for s in screens if "native_background" in s]
    if requested or background_images is not None:
        if (not edit_requested or not isinstance(background_images, dict)
                or any(not isinstance(key, str) for key in requested)
                or len(requested) != len(set(requested)) or set(background_images) != set(requested)
                or any(not isinstance(raw, bytes) for raw in background_images.values())):
            raise HmiError("PREVIEW_BACKGROUND", "Background bytes must exactly cover declared existing-edit pages")
    tags = design.get("tags", [])
    tags = [t for t in tags if isinstance(t, dict)] if isinstance(tags, list) else []
    tag_map = {t["id"]: t for t in tags if isinstance(t.get("id"), str)}
    screen_markup = []
    screen_options = []
    elements_data = []
    invalid_unit_owners = {issue.get("element_id") for issue in issues
                           if issue["code"].startswith("UNIT_LABEL_")
                           and isinstance(issue.get("element_id"), str)}
    invalid_unit_label_indexes = []
    invalid_alarm_views = {issue.get("element_id") for issue in issues
                           if issue["code"].startswith("ALARM_VIEW_")
                           and isinstance(issue.get("element_id"), str)}
    invalid_alarm_view_indexes = []
    source_preserved_alarm_indexes = []
    invalid_native_owners = {issue.get("element_id") for issue in issues
                             if isinstance(issue.get("element_id"), str)}
    native_preserved_indexes = []
    invalid_native_preserved_indexes = []
    native_text_intent_indexes = []
    unit_label_ids = set()
    for screen_index, screen in enumerate(screens):
        width = _int(screen.get("width"), 800, 1)
        height = _int(screen.get("height"), 480, 1)
        screen_options.append(f'<option value="{screen_index}">{_text(screen.get("name", "Unnamed screen"))} · {width} × {height}</option>')
        children = []
        elements = screen.get("elements", [])
        elements = elements if isinstance(elements, list) else []
        for element in elements:
            if not isinstance(element, dict):
                continue
            index = len(elements_data)
            elements_data.append(element)
            kind = element.get("kind")
            kind = kind if isinstance(kind, str) else "unsupported"
            known = kind in KINDS
            css_kind = kind if known else "unsupported"
            geometry = {key: _int(element.get(key), default, minimum)
                        for key, default, minimum in (("x", 0, 0), ("y", 0, 0), ("width", 160, 1), ("height", 48, 1))}
            font_size = _int(element.get("font_size"), 20, 6, 96)
            color = _color(element.get("color"), "#e6edf5")
            fill = _color(element.get("fill"), "#1b293b" if kind != "text" else "#101b2a")
            style = f'left:{geometry["x"]}px;top:{geometry["y"]}px;width:{geometry["width"]}px;height:{geometry["height"]}px;font-size:{font_size}px;color:{color};background:{fill};'
            label = _text(element.get("text", ""))
            reading, note, reading_fill, is_unknown = _initial_state(element, tag_map, values or {}, states or {}, valid)
            if kind in {"numeric_input", "numeric_display"} and "unit_label" in element:
                if isinstance(element["unit_label"], str):
                    unit_label_ids.add(element["unit_label"])
                if isinstance(element.get("id"), str) and element["id"] in invalid_unit_owners:
                    invalid_unit_label_indexes.append(index)
                    reading, note, reading_fill, is_unknown = "UNKNOWN", "UNIT LABEL INVALID", "#303d4e", True
            if kind in {"button", "indicator", "numeric_input", "numeric_display"}:
                style = re.sub(r"background:[^;]+;", f"background:{reading_fill};", style)
                if is_unknown:
                    css_kind += " unknown"
            if kind == "text":
                content = f'<span class="label">{label}</span>'
                if native_candidate_requested:
                    native_text_intent_indexes.append(index)
            elif kind in {"numeric_input", "numeric_display"}:
                binding = element.get("binding", {})
                binding = binding if isinstance(binding, dict) else {}
                unit_tag_id = binding.get("write") if kind == "numeric_input" else binding.get("read")
                unit_tag = tag_map.get(unit_tag_id, {}) if isinstance(unit_tag_id, str) else {}
                unit = _text(element.get("unit", unit_tag.get("unit", "")))
                unit_markup = "" if "unit_label" in element else f'<span class="unit">{unit}</span>'
                content = f'<span class="element-title">{label}</span><span class="reading"><span class="value">{_text(reading)}</span>{unit_markup}</span><span class="quality"{ " hidden" if not note else ""}>{_text(note)}</span>'
            elif kind in {"button", "indicator"}:
                content = f'<span class="element-title">{label}</span><span class="value">{_text(reading)}</span><span class="quality"{ " hidden" if not note else ""}>{_text(note)}</span>'
            elif kind == "goto":
                content = f'<span class="label">{label} <span aria-hidden="true">→</span></span><span class="quality">NAVIGATION ILLUSTRATION</span>'
            elif kind in {"native_preserved", "native_presentation", "native_integer_numeric", "native_entry_permission", "native_control_clone"}:
                native_preserved_indexes.append(index)
                invalid_owner = not isinstance(element.get("id"), str) or element["id"] in invalid_native_owners
                if invalid_owner:
                    invalid_native_preserved_indexes.append(index)
                title = ("SOURCE CLONE" if kind == "native_control_clone" else "SOURCE OBJECT") + (" INVALID" if invalid_owner else "")
                css_kind += " unknown source-object"
                style = re.sub(r"font-size:[^;]+;color:[^;]+;background:[^;]+;",
                               "font-size:20px;color:#e6edf5;background:#303d4e;", style)
                content = f'<span class="element-title">{title}</span><span class="value">UNKNOWN</span><span class="quality">NATIVE NOT RENDERED</span>'
            elif kind.startswith("alarm_"):
                invalid_view = isinstance(element.get("id"), str) and element["id"] in invalid_alarm_views
                if invalid_view:
                    invalid_alarm_view_indexes.append(index)
                if "view_policy" in element:
                    source_preserved_alarm_indexes.append(index)
                    # These are engineering placeholders, not a recreation of
                    # the source-native font, color or table presentation.
                    style = re.sub(r"font-size:[^;]+;color:[^;]+;background:[^;]+;",
                                   "font-size:20px;color:#e6edf5;background:#303d4e;", style)
                title, reading, note, alarm_class = _initial_alarm(element, design.get("alarms", []), tag_map, values or {}, states or {}, valid, invalid_view)
                css_kind += " " + alarm_class
                content = f'<span class="element-title">{_text(title)}</span><span class="value">{_text(reading)}</span><span class="quality"{ " hidden" if not note else ""}>{_text(note)}</span>'
            else:
                content = '<span class="value">UNSUPPORTED LAYER</span><span class="quality">NOT RENDERED AS NATIVE</span>'
            presentation = ' data-native-presentation="text-intent-only"' if native_candidate_requested and kind == "text" else ""
            children.append(f'<div class="element {css_kind}" data-index="{index}" data-element-id="{_text(element.get("id", index))}"{presentation} style="{style}" role="img" aria-label="Conceptual illustration: {_text(element.get("text", kind))}">{content}</div>')
        hidden = " hidden" if screen_index else ""
        background_markup = ""
        if background_images is not None:
            import base64
            from .native.existing_background import decode_opaque_png
            raw = background_images.get(screen.get("native_id"))
            if raw is not None:
                import hashlib
                declaration = screen.get("native_background")
                if (not isinstance(raw, bytes) or not isinstance(declaration, dict)
                        or hashlib.sha256(raw).hexdigest() != declaration.get("asset_sha256")):
                    raise HmiError("PREVIEW_BACKGROUND", "Background illustration differs from its declared PNG pin")
                decode_opaque_png(raw, width, height)
                encoded = base64.b64encode(raw).decode("ascii")
                background_markup = f'<img data-native-background="requested-opaque-png-only" src="data:image/png;base64,{encoded}" width="{width}" height="{height}" style="position:absolute;left:0;top:0;width:{width}px;height:{height}px" alt="Requested background only; native controls and glyphs are not rendered">'
        screen_markup.append(f'<section class="screen" data-screen="{screen_index}" data-width="{width}" data-height="{height}" style="width:{width}px;height:{height}px"{hidden}>{background_markup}{"".join(children)}</section>')
    tag_rows = []
    for index, tag in enumerate(tags):
        tag_rows.append(f'<label class="tag-control"><span><strong>{_text(tag.get("id", "Unnamed"))}</strong><small>{_text(tag.get("data_type", "UNKNOWN"))} · {_text(tag.get("unit", ""))}</small></span><input data-tag="{index}" aria-label="Sample value for {_text(tag.get("id", "Unnamed"))}" autocomplete="off" placeholder="No sample"><select data-quality="{index}" aria-label="Sample quality for {_text(tag.get("id", "Unnamed"))}"><option value="valid">Valid sample</option><option value="invalid">Invalid</option><option value="stale">Stale</option></select></label>')
    issue_markup = "".join(f'<li><code>{_text(i["code"])}</code> {_text(i["message"])}</li>' for i in issues)
    issues_html = f'<details class="issues"><summary>{len(issues)} common-model validation issue(s) — production blocked</summary><ul>{issue_markup}</ul></details>' if issues else '<p class="validation">Common-model validation passed. Vendor and physical acceptance remain separate.</p>'
    invalid_values = [tid for tid in tag_map if not _sample(tid, tag_map, values or {}, {}, True)[0]]
    data = {"elements": elements_data, "tags": tags, "values": values or {}, "states": states or {},
            "invalid_values": invalid_values,
            "invalid_unit_label_indexes": invalid_unit_label_indexes,
            "invalid_alarm_view_indexes": invalid_alarm_view_indexes,
            "source_preserved_alarm_indexes": source_preserved_alarm_indexes,
            "native_preserved_indexes": native_preserved_indexes,
            "invalid_native_preserved_indexes": invalid_native_preserved_indexes,
            "native_preserved_count": len(native_preserved_indexes),
            "unit_label_indexes": [index for index, element in enumerate(elements_data)
                                   if element.get("kind") == "text" and isinstance(element.get("id"), str)
                                   and element["id"] in unit_label_ids],
            "valid": bool(valid), "numeric": NUMERIC, "alarms": design.get("alarms", [])}
    if native_candidate_requested:
        # Presence is a request, never calibration or native pixel acceptance.
        # The banner remains visible even when the profile/IR is unqualified.
        data["native_candidate_presentation"] = {
            "policy": "RETAIN_SOURCE_APPEARANCE", "render_kind": "CONCEPTUAL_IR",
            "native_visual_acceptance": "NOT_RUN", "text_intent_indexes": native_text_intent_indexes}
        if edit_requested:
            data["native_candidate_presentation"]["policy"] = (
                "REQUESTED_BACKGROUND_ONLY_CONTROLS_NOT_RENDERED" if requested
                else "NO_BACKGROUND_REQUESTED_CONTROLS_NOT_RENDERED")
    replacements = {
        "__TITLE__": _text(design.get("project_id", "Conceptual preview")),
        "__PROFILE__": _text(profile.get("id", "unknown profile")),
        "__EVIDENCE__": _text("Synthetic fixture · no vendor-native source" if profile.get("fixture_kind") == "synthetic" else "Conceptual view · native acceptance not asserted"),
        "__ISSUES__": issues_html, "__SCREENS__": "".join(screen_markup),
        "__SCREEN_OPTIONS__": "".join(screen_options), "__TAGS__": "".join(tag_rows),
        "__DATA__": _safe_json(data),
        "__UNIT_LABEL_NOTE__": "Unit label fitting checks the conceptual browser font only; native font and pixel qualification remain separate." if unit_label_ids else "",
        "__ALARM_VIEW_NOTE__": "SOURCE-PRESERVED PRESENTATION: alarm views are placeholders. Source-native fonts, table columns, timestamps, history storage and actions are neither rendered nor qualified here." if source_preserved_alarm_indexes else "",
        "__NATIVE_PRESERVED_NOTE__": (f"{len(native_preserved_indexes)} source object/clone declaration(s): native appearance, addresses and actions are not rendered. Stored cloning is separate from logical process, runtime and generic control qualification." if any(e.get("kind") == "native_control_clone" for e in elements_data) else f"{len(native_preserved_indexes)} source object declaration(s): retention only, not feature emission. Native appearance, addresses and actions are neither rendered nor qualified here.") if native_preserved_indexes else "",
        "__NATIVE_CANDIDATE_BANNER__": '<p class="native-candidate-note" role="note"><strong>TEXT INTENT ONLY</strong> · Native editing retains existing source appearance; native appearance is not rendered here. Literal text and coordinates show the requested change. Browser fonts, colors, backgrounds and fitting do not represent the retained native glyphs or pixels. This notice does not attest calibration, vendor or panel acceptance.</p>' if native_candidate_requested else "",
        "__QUALIFICATION_NOTE__": "Additional request-state indicator is an offline qualification example." if profile.get("fixture_kind") == "synthetic" and any(e.get("kind") == "indicator" and e.get("role") == "request" for e in elements_data) else "",
    }
    if edit_requested:
        heading = "BACKGROUND ONLY" if requested else "NO BACKGROUND REQUESTED"
        background_note = ("The pinned requested opaque PNG is shown at its exact canvas size. " if requested
                           else "No background replacement was requested; the source background is not rendered. ")
        replacements["__NATIVE_CANDIDATE_BANNER__"] = f'<p class="native-candidate-note" role="note"><strong>{heading} · NATIVE CONTROLS NOT RENDERED</strong> · {background_note}Source controls are UNKNOWN placeholders at the requested coordinates. Native fonts, shapes, color states, transparency and the final composite are not rendered or visually accepted here. Stored-file validation and human vendor/panel acceptance remain separate.</p>'
    if isinstance(candidate_spec, dict) and candidate_spec.get("mode") == "diascreen_control_append":
        replacements["__NATIVE_CANDIDATE_BANNER__"] = '<p class="native-candidate-note" role="note"><strong>SOURCE CLONES · NATIVE NOT RENDERED</strong> · New ID, rectangle and declared button captions are stored-file intent only. Original addresses are shared with existing controls and macros. Samples, numeric process semantics, runtime states and native appearance are not represented.</p>'
    # One pass avoids treating marker-looking user text as template instructions.
    return re.sub(r"__[A-Z_]+__", lambda match: replacements.get(match.group(), match.group()), _HTML)


_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>__TITLE__ · Conceptual HMI preview</title>
<style>
:root{color-scheme:dark;font-family:Segoe UI,Arial,sans-serif;background:#0b1220;color:#e6edf5}*{box-sizing:border-box}body{margin:0}header{padding:24px 32px 18px;border-bottom:1px solid #263448;background:#111d2e}.eyebrow{color:#f0bc6f;font-size:11px;letter-spacing:1.8px;font-weight:700}h1{font-size:24px;margin:8px 0;font-weight:600}header p{color:#a5b5c9;font-size:13px;line-height:1.5;margin:4px 0}.workspace{display:grid;grid-template-columns:minmax(480px,1fr) 330px;gap:22px;padding:24px 32px}.preview-column{min-width:0}.toolbar{display:flex;gap:12px;align-items:center;margin-bottom:14px;font-size:12px;color:#a5b5c9}.toolbar select{flex:1;max-width:320px}.badge{border:1px solid #3c526c;border-radius:20px;padding:5px 10px;font-size:10px;letter-spacing:.8px;white-space:nowrap}.frame{background:#070e19;border:1px solid #2a3c54;border-radius:12px;padding:18px;overflow:hidden;box-shadow:0 20px 45px #0005}.viewport{position:relative;overflow:hidden;margin:auto}.screen{position:absolute;transform-origin:top left;background:#101b2a;overflow:hidden}.screen[hidden]{display:none}.element{position:absolute;border-radius:9px;display:flex;flex-direction:column;justify-content:center;padding:10px 16px;overflow:hidden;user-select:none;pointer-events:none;line-height:1.12}.element.text{padding:0;display:flex;justify-content:center;border-radius:0}.element.text .label{white-space:pre-wrap}.element-title{font-size:11px;letter-spacing:.65px;opacity:.82;line-height:1.2;margin-bottom:6px;overflow:hidden}.reading{display:flex;gap:10px;align-items:baseline;white-space:nowrap;min-width:0}.value{font-weight:600;white-space:nowrap;max-width:100%;font-variant-numeric:tabular-nums;line-height:1.1}.reading .value{flex:0 0 auto;min-width:0}.unit{font-size:13px;color:#a5b5c9;flex:none}.quality{font-size:11px;font-weight:500;letter-spacing:.55px;margin-top:7px;opacity:.7;line-height:1.2}.button,.goto{border:1px solid #526d8c;box-shadow:inset 0 -3px 0 #0002}.button .value,.indicator .value{font-size:inherit}.indicator{border-left:4px solid #67778c}.unknown{background:#303d4e!important;border-color:#738095!important;color:#e5eaf1!important}.unknown .quality{color:#d3d9e2;opacity:1}.element-title,.quality,.reading,.element>.value{flex-shrink:0}.quality[hidden]{display:none}.alarm_strip{padding:6px 16px}.alarm_strip .element-title{margin-bottom:3px;font-size:10px}.alarm_strip .quality{margin-top:3px;font-size:11px}.alarm_strip.active,.alarm_table.active{background:#3b2e22!important;border-left:4px solid #d9ab5f;color:#f2d5ad!important}.layout-error{border:1px solid #d9ab5f}.layout-report{color:#f0bc6f;background:#352a23;border:1px solid #6b4a32;border-radius:7px;padding:12px;font-size:12px;line-height:1.5}.unsupported{background:#493b32!important;color:#f0bc6f!important;border:1px dashed #d09856}.caption{color:#8296ae;font-size:11px;line-height:1.6;margin:12px 2px}.validation{font-size:11px;color:#92a9bf;line-height:1.5}.issues{background:#352a23;border:1px solid #6b4a32;padding:12px;border-radius:7px;color:#efc49d;font-size:11px;margin-top:12px}.issues summary{cursor:pointer}.issues li{margin:6px 0;line-height:1.5}.issues code{color:#f0bc6f}.controls{background:#111d2e;border:1px solid #263448;border-radius:10px;padding:20px;align-self:start}.controls h2{font-size:16px;font-weight:600;margin:0 0 8px}.controls p{font-size:12px;color:#95a8bf;line-height:1.6;margin:0 0 18px}.global{display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid #2a3a4e;padding-bottom:15px;margin-bottom:5px;font-size:12px}.tag-control{display:grid;grid-template-columns:1fr 88px;gap:8px;padding:14px 0;border-bottom:1px solid #22334a}.tag-control>span{min-width:0}.tag-control strong{display:block;overflow-wrap:anywhere;font-size:11px;font-weight:500}.tag-control small{display:block;color:#8aa0b8;font-size:10px;margin-top:5px}.tag-control select{grid-column:1/-1;width:100%}input,select{color:#dfe8f4;background:#0c1727;border:1px solid #354b65;border-radius:5px;padding:8px;font-family:inherit;font-size:11px;min-width:0}input:focus,select:focus{outline:2px solid #74b4f0;outline-offset:1px}.controls .footnote{margin-top:16px;margin-bottom:0;font-size:10px}.empty{padding:40px;color:#a5b5c9}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}@media(max-width:1050px){.workspace{grid-template-columns:1fr;padding:20px}.controls{max-width:none}.tag-control{grid-template-columns:minmax(100px,1fr) 100px 150px}.tag-control select{grid-column:auto}.frame{padding:12px}header{padding:20px}}@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head><body>
<header><span class="eyebrow">OFFLINE ENGINEERING PREVIEW</span><h1>__TITLE__</h1><p>Conceptual only · no native vendor rendering · no live controller connection.</p><p>__PROFILE__ · __EVIDENCE__</p>__NATIVE_CANDIDATE_BANNER__</header>
<main class="workspace"><div class="preview-column"><div class="toolbar"><label for="screen-select">Screen</label><select id="screen-select">__SCREEN_OPTIONS__</select><span class="badge">ILLUSTRATION</span></div><div class="frame"><div class="viewport" id="viewport">__SCREENS__</div></div><p class="caption">Panel elements are illustrations. Inspect request, feedback and invalid states with the external sample controls. Button behavior, macros, navigation and alarm retention are not executed here. __QUALIFICATION_NOTE__ __UNIT_LABEL_NOTE__ __ALARM_VIEW_NOTE__ __NATIVE_PRESERVED_NOTE__</p><p class="layout-report" id="layout-issues" hidden role="alert"></p>__ISSUES__</div><aside class="controls"><h2>Sample controls</h2><p>These controls belong to this preview, outside the HMI. Values are samples, never controller observations.</p><label class="global"><span>All sample quality</span><select id="global-quality"><option value="per_tag">Per tag</option><option value="invalid">Invalid</option><option value="stale">Stale</option></select></label><div>__TAGS__</div><p class="footnote">Missing, malformed, out-of-range or stale data displays gray UNKNOWN. Alarm history has no persisted sample store.</p></aside></main>
<script id="preview-data" type="application/json">__DATA__</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById('preview-data').textContent);
const inputs=[...document.querySelectorAll('[data-tag]')];
const qualities=[...document.querySelectorAll('[data-quality]')];
const values=Object.assign(Object.create(null),data.values);
const quality=Object.assign(Object.create(null),data.states);
const invalidValues=new Set(data.invalid_values);
const invalidUnitLabels=new Set(data.invalid_unit_label_indexes);
const unitLabels=new Set(data.unit_label_indexes);
const invalidAlarmViews=new Set(data.invalid_alarm_view_indexes);
const sourcePreservedAlarms=new Set(data.source_preserved_alarm_indexes);
const nativePreserved=new Set(data.native_preserved_indexes);
const invalidNativePreserved=new Set(data.invalid_native_preserved_indexes);
const tags=new Map(data.tags.filter(t=>typeof t.id==='string').map(t=>[t.id,t]));
const nodes=[...document.querySelectorAll('[data-index]')];
const allQuality=document.getElementById('global-quality');
const screenSelect=document.getElementById('screen-select');
let layoutReports=[];
function hex(value,fallback){return typeof value==='string'&&/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(value)?value:fallback;}
function tagSample(id){
 const tag=tags.get(id),v=values[id];
 const q=allQuality.value==='per_tag'?(quality[id]||'valid'):allQuality.value;
 if(!data.valid||!tag||q!=='valid'||invalidValues.has(id)||typeof v!=='number'||!Number.isFinite(v))return {ok:false,reason:q==='stale'?'STALE':'INVALID / MISSING'};
 if(tag.data_type==='BOOL')return {ok:v===0||v===1,value:v,reason:'INVALID BOOL'};
 const limits=data.numeric[tag.data_type];
 if(!Array.isArray(limits)||v<limits[0]||v>limits[1]||(limits[2]===0&&!Number.isInteger(v)))return {ok:false,reason:'TYPE / RANGE'};
 return {ok:true,value:v};
}
function fixedDisplay(value,digits){
 if(!Number.isSafeInteger(value)||!Number.isInteger(digits)||digits<0||digits>15)return null;
 const sign=value<0?'-':'';
 let text=String(Math.abs(value));
 if(digits===0)return sign+text;
 text=text.padStart(digits+1,'0');
 return sign+text.slice(0,-digits)+'.'+text.slice(-digits);
}
function unknown(node,reason){
 node.classList.add('unknown');
 const value=node.querySelector('.value');if(value)value.textContent='UNKNOWN';
 setQuality(node,reason);
}
function setQuality(node,text){const note=node.querySelector('.quality');if(note){note.textContent=text;note.hidden=!text;}}
function rangeBounds(value){const range=document.createRange();range.selectNodeContents(value);return range.getBoundingClientRect();}
function contentBox(node){
 const box=node.getBoundingClientRect(),style=getComputedStyle(node),scale=box.width/node.offsetWidth||1;
 return {left:box.left+(parseFloat(style.borderLeftWidth)+parseFloat(style.paddingLeft))*scale,
 right:box.right-(parseFloat(style.borderRightWidth)+parseFloat(style.paddingRight))*scale,
 top:box.top+(parseFloat(style.borderTopWidth)+parseFloat(style.paddingTop))*scale,
 bottom:box.bottom-(parseFloat(style.borderBottomWidth)+parseFloat(style.paddingBottom))*scale,scale};
}
function fit(node){
 if(nativePreserved.has(Number(node.dataset.index))){
  const box=contentBox(node);
  const required=[...node.children].filter(c=>!c.hidden);
  if(required.some(child=>{const bounds=rangeBounds(child);return bounds.left<box.left-0.5||bounds.right>box.right+0.5||bounds.top<box.top-0.5||bounds.bottom>box.bottom+0.5;})){
   node.classList.add('layout-error');
   layoutReports.push('INSUFFICIENT SPACE — '+node.dataset.elementId+': source object placeholder does not fit. Native rendering remains unqualified.');
  }
  return;
 }
 if(sourcePreservedAlarms.has(Number(node.dataset.index))){
  const box=contentBox(node);
  const required=[...node.children].filter(c=>!c.hidden);
  if(required.some(child=>{const bounds=rangeBounds(child);return bounds.left<box.left-0.5||bounds.right>box.right+0.5||bounds.top<box.top-0.5||bounds.bottom>box.bottom+0.5;})){
   node.classList.add('layout-error');
   layoutReports.push('INSUFFICIENT SPACE — '+node.dataset.elementId+': source-preserved presentation placeholder does not fit. Native rendering remains unqualified.');
  }
  return;
 }
 if(node.classList.contains('text')&&unitLabels.has(Number(node.dataset.index))){
  const label=node.querySelector('.label'),element=data.elements[Number(node.dataset.index)];if(!label)return;
  const full=typeof element.text==='string'?element.text:'';label.textContent=full;
  const box=contentBox(node),bounds=rangeBounds(label);
  if(bounds.left<box.left-0.5||bounds.right>box.right+0.5||bounds.top<box.top-0.5||bounds.bottom>box.bottom+0.5){
   node.classList.add('layout-error');node.title=full;
   layoutReports.push('INSUFFICIENT SPACE — '+node.dataset.elementId+': unit label cannot fit at its declared font size. Full text is retained in the design.');
   label.textContent='INSUFFICIENT SPACE';
  }
  return;
 }
 const value=node.querySelector('.value');if(!value)return;
 let size=parseInt(getComputedStyle(node).fontSize,10)||20;
 const alarm=node.classList.contains('alarm_strip')||node.classList.contains('alarm_table')||node.classList.contains('alarm_history');
 if(alarm)size=Math.max(14,size);
 value.style.fontSize=size+'px';
 value.style.whiteSpace=alarm?'normal':'nowrap';value.style.overflowWrap=alarm?'anywhere':'normal';value.style.lineHeight=alarm?'1.25':'1.1';
 const fits=()=>{
  const box=contentBox(node),bounds=rangeBounds(value);
  const unit=node.querySelector('.unit'),unitBounds=unit?rangeBounds(unit):null;
  if(bounds.left<box.left-0.5||bounds.right>box.right+0.5||(unitBounds&&unitBounds.right>box.right+0.5))return false;
  if(alarm){
   const required=[...node.children].filter(c=>!c.hidden).reduce((total,c)=>{const style=getComputedStyle(c);return total+c.getBoundingClientRect().height/box.scale+parseFloat(style.marginTop)+parseFloat(style.marginBottom);},0);
   return required<=(box.bottom-box.top)/box.scale+0.5;
  }
  return bounds.top>=box.top-0.5&&bounds.bottom<=box.bottom+0.5;
 };
 const minimum=alarm?14:10;
 while(size>minimum&&!fits()){size--;value.style.fontSize=size+'px';}
 if(alarm&&!fits()){
  const full=value.textContent;node.classList.add('layout-error');node.title=full;
  layoutReports.push('INSUFFICIENT SPACE — '+node.dataset.elementId+': alarm text cannot fit at 14px or larger. Full text is retained in the design.');
  value.textContent='INSUFFICIENT SPACE';value.style.fontSize='14px';setQuality(node,'');
 }
}
function render(){
 layoutReports=[];
 nodes.forEach(node=>{
  if(node.closest('.screen').hidden)return;
  const element=data.elements[Number(node.dataset.index)],kind=element.kind,binding=element.binding||{};
  node.classList.remove('unknown','active','layout-error');node.removeAttribute('title');node.style.background=hex(element.fill,kind==='text'?'#101b2a':'#1b293b');
   if(kind==='native_preserved'||kind==='native_presentation'||kind==='native_integer_numeric'||kind==='native_entry_permission'||kind==='native_control_clone'){
   const sourceTitle=kind==='native_control_clone'?'SOURCE CLONE':'SOURCE OBJECT';
   node.querySelector('.element-title').textContent=sourceTitle+(invalidNativePreserved.has(Number(node.dataset.index))?' INVALID':'');
   node.style.fontSize='20px';node.style.color='#e6edf5';
   unknown(node,'NATIVE NOT RENDERED');fit(node);return;
  }else if(kind==='button'||kind==='indicator'){
   // A write-only command is not feedback. A sample read binding is mandatory to illustrate state.
   const sample=tagSample(binding.read);
   if(!sample.ok){unknown(node,sample.reason||'NO READ SAMPLE');fit(node);return;}
   const states=Array.isArray(element.states)?element.states:[];
   const state=states.find(s=>s&&s.value===sample.value);
   if(!state||typeof state.text!=='string'){unknown(node,'STATE UNDEFINED');fit(node);return;}
   node.querySelector('.value').textContent=state.text;
   node.style.background=hex(state.fill,'#303d4e');
   setQuality(node,'');
  }else if(kind==='numeric_input'||kind==='numeric_display'){
   if(invalidUnitLabels.has(Number(node.dataset.index))){unknown(node,'UNIT LABEL INVALID');fit(node);return;}
   if(kind==='numeric_input'){
    const readTag=tags.get(binding.read),writeTag=tags.get(binding.write);
    if(!readTag||!writeTag||binding.read!==binding.write||readTag.data_type!==writeTag.data_type||(readTag.unit||'')!==(writeTag.unit||'')||writeTag.access!=='ReadWrite'){
     unknown(node,'INPUT BINDING INVALID');fit(node);return;
    }
   }
   const sample=tagSample(binding.read);
   if(!sample.ok||(typeof element.minimum==='number'&&sample.value<element.minimum)||(typeof element.maximum==='number'&&sample.value>element.maximum)){
    unknown(node,sample.reason||'ELEMENT RANGE');fit(node);return;
   }
   const digits=Number.isInteger(element.fractional)&&element.fractional>=0&&element.fractional<=15?element.fractional:0;
   const rendered=element.value_model==='integer_fixed_decimal'?fixedDisplay(sample.value,digits):sample.value.toFixed(digits);
   if(rendered===null){unknown(node,'VALUE MODEL INVALID');fit(node);return;}
   node.querySelector('.value').textContent=rendered;
   setQuality(node,'');
  }else if(typeof kind==='string'&&kind.startsWith('alarm_')){
   if(sourcePreservedAlarms.has(Number(node.dataset.index))){
    const invalid=invalidAlarmViews.has(Number(node.dataset.index))||element.view_policy!=='preserve_source';
    node.querySelector('.element-title').textContent=invalid?'ALARM VIEW POLICY INVALID':'SOURCE-PRESERVED PRESENTATION';
    unknown(node,invalid?'NATIVE VIEW NOT RENDERED':kind==='alarm_history'?'NO HISTORY DATA':'NATIVE VIEW NOT RENDERED');
    fit(node);return;
   }
   node.querySelector('.element-title').textContent=element.text||'ALARMS';
   if(kind==='alarm_history'){unknown(node,'NO HISTORY DATA');fit(node);return;}
   const alarms=Array.isArray(data.alarms)?data.alarms:[];
   const sampled=alarms.map(a=>({alarm:a,sample:a&&typeof a==='object'&&!Array.isArray(a)&&typeof a.tag==='string'&&tags.get(a.tag)?.data_type==='BOOL'?tagSample(a.tag):{ok:false,reason:'ALARM BINDING INVALID'}}));
   if(!sampled.length||sampled.some(a=>!a.sample.ok)){unknown(node,sampled.some(a=>a.sample.reason==='STALE')?'STALE':'ALARM DATA UNKNOWN');fit(node);return;}
   const active=sampled.filter(a=>a.sample.value===1);
   node.classList.toggle('active',active.length>0);
   node.querySelector('.element-title').textContent=active.length?'ACTIVE ALARMS · '+active.length:'ALARMS · 0 ACTIVE';
   node.querySelector('.value').textContent=active.length?active.map(a=>String(a.alarm.text)).join(' · '):'No active alarms';
   setQuality(node,'');
  }
  fit(node);
 });
 const report=document.getElementById('layout-issues');report.textContent=layoutReports.join(' ');report.hidden=layoutReports.length===0;
}
inputs.forEach((input,index)=>{
 const id=data.tags[index].id;
 const initial=Object.prototype.hasOwnProperty.call(values,id)?values[id]:null;
 input.value=typeof initial==='number'&&Number.isFinite(initial)?String(initial):'';
 const q=quality[id];qualities[index].value=['valid','invalid','stale'].includes(q)?q:'invalid';
 if(q===undefined)qualities[index].value='valid';
 input.addEventListener('input',()=>{const raw=input.value.trim();const tag=tags.get(id);const integer=tag&&(tag.data_type==='BOOL'||Array.isArray(data.numeric[tag.data_type])&&data.numeric[tag.data_type][2]===0);const grammar=integer?/^[+-]?\d+$/:/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;values[id]=raw!==''&&grammar.test(raw)?Number(raw):null;invalidValues.delete(id);render();});
 qualities[index].addEventListener('change',()=>{quality[id]=qualities[index].value;render();});
});
function resize(){
 const screen=document.querySelector('.screen:not([hidden])');
 const viewport=document.getElementById('viewport');
 if(!screen){viewport.innerHTML='<p class="empty">No screen supplied.</p>';return;}
 const width=Number(screen.dataset.width),height=Number(screen.dataset.height);
 const available=viewport.parentElement.clientWidth-parseFloat(getComputedStyle(viewport.parentElement).paddingLeft)*2;
 const scale=Math.min(1,available/width);
 viewport.style.width=Math.floor(width*scale)+'px';viewport.style.height=Math.floor(height*scale)+'px';screen.style.transform='scale('+scale+')';
 render();
}
screenSelect.addEventListener('change',()=>{document.querySelectorAll('.screen').forEach(screen=>{screen.hidden=screen.dataset.screen!==screenSelect.value;});resize();});
allQuality.addEventListener('change',render);window.addEventListener('resize',resize);resize();
</script></body></html>'''
