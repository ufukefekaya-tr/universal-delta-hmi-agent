"""The original, vendor-independent design model.

Designs are JSON data. A hash describes exact design intent, never vendor or
physical qualification. No address or controller behavior is inferred here.
Numeric ``unit_label`` references an explicitly placed, separately owned text
element on the same screen; the relationship is part of the full design hash.
Explicit ``value_model="integer_fixed_decimal"`` keeps numeric bounds and
samples in raw PLC integer units; ``fractional`` declares decimal position per
element. Exact common arithmetic is not native compiler/keypad qualification.
Alarm ``history_policy="preserve_source"`` retains the source storage contract.
Alarm views may declare ``view_policy="preserve_source"`` with empty text and
geometry only; source-native fonts, columns, timestamps and actions are not
inferred by the common model or its conceptual preview.
``native_preserved`` represents an existing opaque source object, not a new
feature or an emitted object. Its canonical native ID, complete source-owner
SHA-256 and exact source geometry are declared explicitly; only the service
can verify those against immutable native bytes. Presentation, bindings and
actions remain unmodeled, and the preview displays an UNKNOWN placeholder.
``native_control_clone`` is a separate stored-file declaration for a new copy
of an immutable source donor. Its ``clone`` identifies the source-pinned donor
kind and the primary 0/1 captions for buttons. ID and geometry are explicit;
every binding, numeric setting, style and action remains unchanged. It does
not establish logical process/read semantics, allocate memory, or qualify
ordinary button/numeric capabilities. The preview shows a source-clone
placeholder without values or runtime states.
``native_integer_numeric`` adds separately qualified existing WORD numeric
settings to a source-pinned owner. Its explicit ``integer_numeric`` object
contains INT/UINT storage identity, integer_fixed_decimal, I/F digits and input
raw integer limits only. Original storage, scale, addresses and units remain
immutable. ``presentation`` is explicit ({} means geometry only); native
controls are not rendered by the conceptual preview.
An optional ``entry_permission`` combines the separately qualified stored
entry/keypad-open permission request with those same-owner numeric settings.
``native_entry_permission`` is a distinct source-pinned declaration with
explicit ``presentation`` and ``entry_permission`` objects. Permission carries
a canonical external address, exact 0/1 enable level and the SHA-256 of a
project-owned source/action classification artifact. It does not infer action
role, namespace authority, read success, sample age, safety or runtime behavior.
Native source gates separately verify owner classification, native link and
namespace authority; runtime and safety acceptance remain separate. The
conceptual preview remains UNKNOWN and does not execute or simulate permission.
Commit-time and continuous checks, quality AND and stale-data handling are not
qualified by this entry-only intent.

``native_presentation`` is a distinct existing-owner edit declaration. Geometry
is the desired rectangle; presentation carries explicit native style/state
scalar requests, pinned to original owner and State hashes. It cannot override
captions, addresses, numeric storage, actions or command semantics. Screen
``native_background`` pins an original fixed DIB frame and a relative PNG asset
path/SHA; native emission validates page ownership and opaque same-size pixels.
These declarations are stored-file intent, never native pixel acceptance.
"""

import hashlib
import json

from .errors import HmiError


def canonical_hash(value):
    """Hash sorted UTF-8 JSON; reject values JSON cannot represent faithfully."""
    try:
        data = json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise HmiError("INVALID_JSON", "Hash input must be finite JSON data") from exc
    return hashlib.sha256(data).hexdigest()


def new_project(project_id, profile_id):
    """Create an empty design; screens and exact controller tags are explicit."""
    if not all(isinstance(value, str) and value.strip() == value and value
               for value in (project_id, profile_id)):
        raise HmiError("INVALID_ID", "Project and profile IDs must be nonempty strings")
    return {"schema_version": 1, "project_id": project_id, "profile_id": profile_id,
            "screens": [], "tags": [], "macros": [], "alarms": []}
