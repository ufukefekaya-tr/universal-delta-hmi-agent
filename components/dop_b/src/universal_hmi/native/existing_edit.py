"""Compose separately qualified edits against one immutable native source.

Deletion, ordinary scalar presentation and fixed page-DIB replacement retain
their independent source contracts. No intermediate file becomes new donor
authority. The copied document mutator and original raw-span expectation are
different paths; a saved candidate must satisfy both and restore its source.
This is stored-file acceptance, not vendor, runtime or pixel acceptance.
"""
from copy import deepcopy

from ..errors import HmiError
from . import NativeAdapter
from .codec import MAX_PAYLOAD
from .existing_program import ExistingProgram, _bounded
from .existing_presentation import ExistingPresentation
from .existing_background_page import ExistingBackgroundPage
from .existing_integer_numeric import ExistingIntegerNumeric
from .existing_entry_permission import ExistingEntryPermission
from .existing_program import _id


_KINDS = frozenset(("delete_literal", "set_existing_presentation",
                    "set_existing_background", "configure_existing_integer_numeric",
                    "set_existing_entry_permission"))


class ExistingEdit:
    """Original-source deletion/presentation/background composition.

    Every operation pin identifies the original source, even when earlier
    requests change record lengths or delete adjacent owners. Native duplicate
    operations are refused. The public transaction service owns retry policy
    and independently verifies the registered evidence authorities.
    """

    def __init__(self, source, existing_graph_schema, presentation_descriptor,
                 background_descriptor, integer_numeric_descriptor=None, *,
                 entry_permission_descriptor=None, address_namespace_raw=None, action_contract_raw=None):
        self.source = source
        self._source_snapshot = source
        self._graph = ExistingProgram(source, existing_graph_schema)
        self._presentation = ExistingPresentation(source, existing_graph_schema,
                                                   presentation_descriptor)
        self._background = ExistingBackgroundPage(source, existing_graph_schema,
                                                   background_descriptor)
        self._integer_numeric = (None if integer_numeric_descriptor is None else
                                 ExistingIntegerNumeric(source, existing_graph_schema,
                                                        integer_numeric_descriptor))
        self._integer_numeric_snapshot = self._integer_numeric
        optional = (entry_permission_descriptor, address_namespace_raw, action_contract_raw)
        if any(value is None for value in optional) and not all(value is None for value in optional):
            raise HmiError("UNQUALIFIED_EXISTING_ENTRY_PERMISSION",
                           "Entry composition needs its complete optional descriptor and two raw artifacts")
        self._entry_permission = (None if entry_permission_descriptor is None else
                                  ExistingEntryPermission(source, existing_graph_schema,
                                                          entry_permission_descriptor,
                                                          address_namespace_raw, action_contract_raw))
        self._entry_permission_snapshot = self._entry_permission

    def check(self):
        if (self.source is not self._source_snapshot
                or self._graph.source is not self.source
                or self._presentation.source is not self.source
                or self._background.source is not self.source
                or self._integer_numeric is not self._integer_numeric_snapshot
                or (self._integer_numeric is not None and self._integer_numeric.source is not self.source)
                or self._entry_permission is not self._entry_permission_snapshot
                or (self._entry_permission is not None and self._entry_permission.source is not self.source)):
            raise HmiError("INVALID_EXISTING_EDIT_SOURCE",
                           "Composed edits must retain their single original source")
        self._graph.check()
        self._presentation.check()
        self._background.check()
        if self._integer_numeric is not None:
            self._integer_numeric.check()
        if self._entry_permission is not None:
            self._entry_permission.check()
        return True

    def _plan(self, operations, assets):
        _bounded(operations)
        if not isinstance(operations, list) or len(operations) > 4096:
            raise HmiError("INVALID_OPERATIONS", "Composed operations must be a bounded list")
        self.check()
        buckets = {kind: [] for kind in _KINDS}
        for operation in operations:
            name = operation.get("op") if isinstance(operation, dict) else None
            if not isinstance(name, str) or name not in _KINDS:
                raise HmiError("INVALID_EXISTING_EDIT_OPERATION",
                               "Only pinned literal, presentation and background edits are supported")
            buckets[name].append(operation)
        numeric_operations = buckets["configure_existing_integer_numeric"]
        permission_operations = buckets["set_existing_entry_permission"]
        if numeric_operations and self._integer_numeric is None:
            raise HmiError("UNQUALIFIED_EXISTING_INTEGER_NUMERIC",
                           "Existing numeric operations require their optional separate descriptor")
        if permission_operations and self._entry_permission is None:
            raise HmiError("UNQUALIFIED_EXISTING_ENTRY_PERMISSION",
                           "Existing entry operations require their optional separate descriptor and raw contracts")
        deletions = self._graph._deletions(buckets["delete_literal"])
        changes = self._presentation._changes(buckets["set_existing_presentation"])
        # Primitive identity validation occurs before set membership, including
        # no-op presentation requests, so deleting an unchanged target conflicts.
        deleted = {(op["screen_id"], op["element_id"])
                   for op in buckets["delete_literal"]}
        presented = {(op["screen_id"], op["element_id"])
                     for op in buckets["set_existing_presentation"]}
        if deleted & presented:
            raise HmiError("EXISTING_EDIT_CONFLICT",
                           "An original owner cannot be deleted and presented in one plan")
        numeric_targets = {(_id(op.get("screen_id"), "screen_id", 65535),
                            _id(op.get("element_id"), "element_id")) for op in numeric_operations}
        if deleted & numeric_targets:
            raise HmiError("EXISTING_EDIT_CONFLICT",
                           "An original owner cannot be deleted and configured numerically in one plan")
        permission_targets = {(_id(op.get("screen_id"), "screen_id", 65535),
                               _id(op.get("element_id"), "element_id")) for op in permission_operations}
        if deleted & permission_targets:
            raise HmiError("EXISTING_EDIT_CONFLICT",
                           "An original owner cannot be deleted and entry-gated in one plan")
        if self._integer_numeric is not None:
            numeric_changes = self._integer_numeric._changes(numeric_operations)
            if changes.keys() & numeric_changes.keys():
                raise HmiError("EXISTING_EDIT_CONFLICT", "Numeric and presentation requests overlap one original scalar")
            changes.update(numeric_changes)
        if self._entry_permission is not None:
            permission_changes = self._entry_permission._changes(permission_operations)
            if changes.keys() & permission_changes.keys():
                raise HmiError("EXISTING_EDIT_CONFLICT", "Entry and other requests overlap one original scalar")
            changes.update(permission_changes)
        # The background primitive validates the exact referenced asset set;
        # bytes are not admitted into the JSON operation tree or copied blindly.
        frames = self._background.spans(buckets["set_existing_background"], assets)
        offsets = [0]
        for section in self.source.document.sections:
            offsets.append(offsets[-1] + len(section.bytes()))
        deletion_spans = [(offsets[o["start"]], offsets[o["end"]], b"")
                          for o in deletions]
        scalar_spans = self._presentation._spans(changes)
        tail_start = offsets[-1]
        body = self.source.envelope.body
        for start, end, raw in frames:
            if (type(start) is not int or type(end) is not int
                    or not tail_start <= start < end <= len(body)
                    or not isinstance(raw, bytes) or len(raw) != end - start):
                raise HmiError("EXISTING_EDIT_SPAN",
                               "Background must replace one fixed original resource-tail extent")
        spans = sorted(deletion_spans + scalar_spans + frames,
                       key=lambda span: (span[0], span[1]))
        previous_end = 0
        expected_length = len(body)
        for start, end, raw in spans:
            if (type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(body)
                    or not isinstance(raw, bytes)):
                raise HmiError("EXISTING_EDIT_SPAN", "Composed source extent is invalid")
            if start < previous_end:
                raise HmiError("EXISTING_EDIT_CONFLICT", "Composed original source extents overlap")
            previous_end = end
            expected_length += len(raw) - (end - start)
        if expected_length > MAX_PAYLOAD:
            raise HmiError("NATIVE_LIMIT", "Composed native body exceeds its bounded payload")
        return {"deletions": deletions, "changes": changes, "frames": frames,
                "tail_start": tail_start, "spans": spans}

    def spans(self, operations, assets=None):
        """Return validated sorted original BODY spans for read-only integration."""
        return self._plan(operations, {} if assets is None else assets)["spans"]

    def _expected(self, spans):
        body, cursor, result = self.source.envelope.body, 0, []
        for start, end, raw in spans:
            result.extend((body[cursor:start], raw))
            cursor = end
        result.append(body[cursor:])
        return b"".join(result)

    def expected_body(self, operations, assets=None):
        """Build from original raw ranges; never call apply or mutate Document."""
        return self._expected(self.spans(operations, assets))

    def _tail(self, plan):
        tail = bytearray(self.source.document.tail)
        for start, end, raw in plan["frames"]:
            tail[start - plan["tail_start"]:end - plan["tail_start"]] = raw
        return bytes(tail)

    def apply(self, operations, assets=None):
        assets = {} if assets is None else assets
        plan = self._plan(operations, assets)
        if not plan["spans"]:
            return self.source.original
        document = deepcopy(self.source.document)
        # Scalar coordinates still address ORIGINAL section identities here.
        # Applying deletions first would make these indices refer to survivors
        # at different positions; intermediate rebasing is deliberately absent.
        for (section_index, record_index), value in plan["changes"].items():
            document.sections[section_index].records[record_index].set_value(value)
        document.tail = self._tail(plan)
        for owner in sorted(plan["deletions"], key=lambda o: o["start"], reverse=True):
            del document.sections[owner["start"]:owner["end"]]
        body = document.bytes()
        if body != self._expected(plan["spans"]):
            raise HmiError("EXISTING_EDIT_PRESERVATION",
                           "Composed document mutation differs from independent original spans")
        raw = self.source.envelope.encode(body)
        self.verify(NativeAdapter(raw, self.source.family), operations, assets)
        return raw

    def verify(self, candidate, operations=None, assets=None):
        operations = [] if operations is None else operations
        assets = {} if assets is None else assets
        if not isinstance(candidate, NativeAdapter):
            raise HmiError("INVALID_EXISTING_EDIT_CANDIDATE",
                           "Composed verification requires a native candidate adapter")
        candidate._preserved_byte_binding("INVALID_EXISTING_EDIT_CANDIDATE")
        plan = self._plan(operations, assets)
        expected = self._expected(plan["spans"])
        if (candidate.family != self.source.family or candidate.model_id != self.source.model_id
                or candidate.editor_version != self.source.editor_version
                or candidate.envelope.thumbnail != self.source.envelope.thumbnail
                or candidate.envelope.prefix != self.source.envelope.prefix_for_body(expected)
                or candidate.envelope.body != expected
                or candidate.document.tail != self._tail(plan)):
            raise HmiError("EXISTING_EDIT_PRESERVATION",
                           "Candidate differs outside the disjoint original approved extents")
        if not plan["spans"] and candidate.original != self.source.original:
            raise HmiError("EXISTING_EDIT_PRESERVATION",
                           "A composed no-op must preserve the complete original file")
        restored, cursor, delta = [], 0, 0
        for start, end, raw in plan["spans"]:
            saved_start = start + delta
            saved_end = saved_start + len(raw)
            restored.extend((candidate.envelope.body[cursor:saved_start],
                             self.source.envelope.body[start:end]))
            cursor = saved_end
            delta += len(raw) - (end - start)
        restored.append(candidate.envelope.body[cursor:])
        if b"".join(restored) != self.source.envelope.body:
            raise HmiError("EXISTING_EDIT_PRESERVATION",
                           "Complete original-body restoration failed for composed edits")
        return True
