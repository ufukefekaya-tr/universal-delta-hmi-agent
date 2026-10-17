"""Common-model and preview regressions; these are not vendor qualification."""

import copy
import hashlib
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path

from universal_hmi.errors import HmiError
from universal_hmi.model import canonical_hash, new_project
from universal_hmi.preview import render_preview
from universal_hmi.validation import KINDS, validate_design


ROOT = Path(__file__).resolve().parents[1]


def profile(profile_id="synthetic_dopsoft2", resolution=None):
    features = {*KINDS, "alarms", "macros", "macro_trigger:startup", "macro_trigger:clock",
                "macro_trigger:button", "macro_op:assign", "macro_op:bit_on", "macro_op:bit_off", "macro_op:if"}
    return {"id": profile_id, "family": "synthetic", "model": "synthetic qualification target",
            "editor_version": "synthetic", "driver": "SIM", "fixture_kind": "synthetic",
            "resolution": resolution or [800, 480], "numeric_types": ["INT", "UINT", "DINT", "UDINT", "REAL", "LREAL"],
            "capabilities": {feature: "OFFLINE_PASS" for feature in features}}


def design():
    return json.loads((ROOT / "examples" / "neutral_800x480.json").read_text(encoding="utf-8"))


def codes(doc, selected=None):
    return {issue["code"] for issue in validate_design(doc, selected or profile())}


def unit_label_design(kind="numeric_display"):
    doc = new_project("explicit_unit", "synthetic_dopsoft2")
    doc["tags"] = [{"id": "process_value", "address": "DEMO.VALUE", "data_type": "REAL",
                    "access": "ReadWrite" if kind == "numeric_input" else "Read", "unit": "rpm"}]
    numeric = {"id": "numeric_owner", "kind": kind, "x": 20, "y": 20, "width": 200, "height": 90,
               "font_size": 30, "color": "#e6edf5", "fill": "#1b293b", "unit": "rpm",
               "unit_label": "unit_owner", "fractional": 1, "format": "decimal",
               "binding": {"read": "process_value", "write": "process_value" if kind == "numeric_input" else None}}
    if kind == "numeric_input":
        numeric.update(minimum=0, maximum=5000)
    label = {"id": "unit_owner", "kind": "text", "x": 240, "y": 20, "width": 100, "height": 50,
             "font_size": 18, "color": "#95a9c2", "fill": "#101b2a", "text": "rpm"}
    doc["screens"] = [{"id": "overview", "name": "Overview", "width": 800, "height": 480,
                       "elements": [numeric, label]}]
    return doc


def preserved_alarm_design(kind="alarm_strip"):
    doc = new_project("preserved_alarm", "synthetic_dopsoft2")
    doc["tags"] = [{"id": "fault", "address": "DEMO.FAULT", "data_type": "BOOL", "access": "Read"}]
    doc["alarms"] = [{"id": "fault_alarm", "tag": "fault", "text": "Supply fault",
                      "history_policy": "preserve_source"}]
    doc["screens"] = [{"id": "overview", "name": "Overview", "width": 800, "height": 480,
                       "elements": [{"id": "fault_view", "kind": kind, "x": 20, "y": 20,
                                     "width": 600, "height": 140, "text": "", "view_policy": "preserve_source"},
                                    {"id": "fault_heading", "kind": "text", "x": 20, "y": 180,
                                     "width": 600, "height": 40, "text": "Faults", "font_size": 24,
                                     "color": "#e6edf5", "fill": "#101b2a"}]}]
    return doc


def preserved_native_design():
    doc = new_project("retained_source", "synthetic_dopsoft2")
    doc["screens"] = [{"id": "overview", "native_id": "1", "name": "Overview", "width": 800, "height": 480,
                       "elements": [{"id": "source_object", "native_id": "17", "kind": "native_preserved",
                                     "x": 20, "y": 20, "width": 320, "height": 100, "text": "",
                                     "source_owner_sha256": hashlib.sha256(b"original neutral owner").hexdigest()}]}]
    return doc


def native_presentation_design():
    doc=preserved_native_design()
    doc['screens'][0]['elements'][0].update(kind='native_presentation',presentation={
        'visual':{'native_style':0},'states':[{'value':'0','state_sha256':'b'*64,'font_size':24,
            'font_ratio':150,'font_color':0xFFFFFF,'surface_color':1}]})
    return doc


def native_integer_numeric_design():
    doc=native_presentation_design()
    doc['screens'][0]['elements'][0].update(kind='native_integer_numeric',integer_numeric={
        'data_type':'INT','value_model':'integer_fixed_decimal','integer_digits':1,'fractional_digits':4})
    return doc


def native_entry_permission_design(combined_numeric=False):
    doc = native_integer_numeric_design() if combined_numeric else preserved_native_design()
    element = doc["screens"][0]["elements"][0]
    if combined_numeric:
        element["integer_numeric"].update(integer_digits=5, fractional_digits=0,
                                          raw_minimum=-32768, raw_maximum=32767)
    else:
        element["kind"] = "native_entry_permission"
    element["presentation"] = {}
    element["entry_permission"] = {
        "permission_address": "{Link1}0@M10", "enable_level": 1,
        "action_classification_sha256": hashlib.sha256(b"neutral action artifact").hexdigest()}
    return doc


class ExistingEntryPermissionDesignTests(unittest.TestCase):
    def test_valid_entry_intent_is_immutable_and_does_not_infer_namespace_or_role(self):
        for combined in (False, True):
            for address in ("{Link1}0@M0", "{Link2}1@S123", "{Link9999}9999@ZZ99999999999",
                            "{Link1}0@X8", "{Link1}0@D1"):
                # X8/D1 are canonical syntax only, not qualified BOOL/radix
                # authority. Native/source emission must refuse them when the
                # pinned namespace has no corresponding BOOL/read region.
                doc = native_entry_permission_design(combined)
                doc["screens"][0]["elements"][0]["entry_permission"]["permission_address"] = address
                before = copy.deepcopy(doc)
                with self.subTest(combined=combined, address=address):
                    self.assertEqual([], validate_design(doc, profile()))
                    self.assertEqual(before, doc)
                    self.assertEqual([], doc["tags"])
                    self.assertEqual([], doc["macros"])

    def test_permission_payload_is_exact_and_requires_all_three_fields(self):
        for payload in (None, True, [], {}, {"permission_address": "{Link1}0@M10"}):
            doc = native_entry_permission_design()
            doc["screens"][0]["elements"][0]["entry_permission"] = payload
            with self.subTest(payload=payload): self.assertIn("ENTRY_PERMISSION_FIELDS", codes(doc))
        for key in ("permission_address", "enable_level", "action_classification_sha256"):
            doc = native_entry_permission_design()
            del doc["screens"][0]["elements"][0]["entry_permission"][key]
            with self.subTest(missing=key): self.assertIn("ENTRY_PERMISSION_FIELDS", codes(doc))
        for key, value in (("quality", "valid"), ("maximum_age_ms", 100), ("safety", True),
                           ("action_role", "start_request"), ("continuous", True)):
            doc = native_entry_permission_design()
            doc["screens"][0]["elements"][0]["entry_permission"][key] = value
            with self.subTest(extra=key): self.assertIn("ENTRY_PERMISSION_FIELDS", codes(doc))

    def test_permission_address_refuses_alias_expression_internal_and_noncanonical_forms(self):
        for address in (None, True, 123, [], {}, "", "M10", "$10", "{Link1}0@M01", "{Link0}0@M1",
                        "{Link01}0@M1", "{Link10000}0@M1", "{Link1}00@M1", "{Link1}10000@M1",
                        "{Link1}0@m1", "{Link1}0@M-1", "{Link1}0@M+1", "{Link1}0@M1.0",
                        "{Link1}0@M1 AND M2", "{Link1}0@M1[0]", "{Link1}0@M1 ", " {Link1}0@M1",
                        "{Link1}0@M1\n", "{Link1}0@M1\x00", "{Link1}0@Ｍ1", "{Link1}0@M١",
                        "DIA_TAG@{EtherLink1}0.GVL.Permit", "{Link1}0@ABCDEFGHI1",
                        "{Link1}0@M999999999999"):
            doc = native_entry_permission_design()
            doc["screens"][0]["elements"][0]["entry_permission"]["permission_address"] = address
            with self.subTest(address=address): self.assertIn("ENTRY_PERMISSION_ADDRESS", codes(doc))

    def test_permission_level_and_action_digest_have_exact_domains(self):
        for level in (None, False, True, 0.0, 1.0, -1, 2, "0", "1", [], {}):
            doc = native_entry_permission_design()
            doc["screens"][0]["elements"][0]["entry_permission"]["enable_level"] = level
            with self.subTest(level=level): self.assertIn("ENTRY_PERMISSION_LEVEL", codes(doc))
        for level in (0, 1):
            doc = native_entry_permission_design()
            doc["screens"][0]["elements"][0]["entry_permission"]["enable_level"] = level
            self.assertEqual([], validate_design(doc, profile()))
        for digest in (None, True, 64, [], {}, "a" * 63, "a" * 65, "A" * 64, "g" * 64,
                       "a" * 64 + "\n", " a" * 32):
            doc = native_entry_permission_design()
            doc["screens"][0]["elements"][0]["entry_permission"]["action_classification_sha256"] = digest
            with self.subTest(digest=digest): self.assertIn("ENTRY_PERMISSION_ACTION_HASH", codes(doc))

    def test_entry_requires_pinned_source_empty_text_and_explicit_presentation(self):
        for key in ("native_id", "source_owner_sha256", "text", "presentation", "entry_permission"):
            doc = native_entry_permission_design(); del doc["screens"][0]["elements"][0][key]
            with self.subTest(missing=key): self.assertIn("NATIVE_PRESERVED_FIELDS", codes(doc))
        for update, expected in (({"source_owner_sha256": "A" * 64}, "NATIVE_PRESERVED_HASH"),
                                 ({"native_id": "017"}, "NATIVE_PRESERVED_ID"),
                                 ({"text": "PERMISSION ON"}, "NATIVE_PRESERVED_TEXT"),
                                 ({"presentation": None}, "NATIVE_PRESENTATION_FIELDS")):
            doc = native_entry_permission_design(); doc["screens"][0]["elements"][0].update(update)
            with self.subTest(update=update): self.assertIn(expected, codes(doc))
        for key, value in (("binding", {"read": "permission"}), ("behavior", "set_on"), ("states", []),
                           ("role", "feedback"), ("font_size", 24), ("fill", "#0f0"), ("maximum_age_ms", 100)):
            doc = native_entry_permission_design(); doc["screens"][0]["elements"][0][key] = value
            with self.subTest(key=key): self.assertIn("NATIVE_PRESERVED_PROPERTY", codes(doc))

    def test_permission_capability_is_explicit_and_old_kinds_keep_their_gate(self):
        for combined in (False, True):
            for status in (None, True, [], {}, "UNVERIFIED", "UNSUPPORTED", "SYNTHETIC_ONLY"):
                selected = profile(); selected["capabilities"]["native_entry_permission"] = status
                with self.subTest(combined=combined, status=status):
                    self.assertIn("FEATURE_UNSUPPORTED", codes(native_entry_permission_design(combined), selected))
        doc = native_entry_permission_design(True)
        selected = profile(); selected["capabilities"]["native_integer_numeric"] = "UNVERIFIED"
        self.assertIn("FEATURE_UNSUPPORTED", codes(doc, selected))
        selected = profile(); del selected["capabilities"]["native_entry_permission"]
        self.assertEqual([], validate_design(native_integer_numeric_design(), selected))
        for kind in ("native_preserved", "native_presentation", "button", "indicator", "numeric_input", "text"):
            doc = native_entry_permission_design(); element = doc["screens"][0]["elements"][0]
            element["kind"] = kind
            with self.subTest(kind=kind): self.assertIn("KIND_PROPERTY", codes(doc))

    def test_any_permission_or_action_change_invalidates_the_exact_design_digest(self):
        doc = native_entry_permission_design(); digest = canonical_hash(doc)
        for key, value in (("permission_address", "{Link1}0@M11"), ("enable_level", 0),
                           ("action_classification_sha256", "f" * 64)):
            changed = copy.deepcopy(doc)
            changed["screens"][0]["elements"][0]["entry_permission"][key] = value
            with self.subTest(key=key):
                self.assertNotEqual(digest, canonical_hash(changed))
                self.assertEqual([], validate_design(changed, profile()))
        changed = copy.deepcopy(doc); changed["screens"][0]["elements"][0]["source_owner_sha256"] = "a" * 64
        self.assertNotEqual(digest, canonical_hash(changed))

    def test_preview_permission_is_unknown_for_every_sample_and_never_a_live_enable(self):
        for combined in (False, True):
            doc = native_entry_permission_design(combined); selected = profile()
            selected["native_schema"] = {"native_candidate": {"mode": "existing_edit"}}
            for values, states, valid in (({}, {}, True), ({"permission": 0}, {}, True),
                                         ({"permission": 1}, {}, True),
                                         ({"permission": 1}, {"permission": "stale"}, True),
                                         ({"permission": 1}, {}, False)):
                with self.subTest(combined=combined, values=values, valid=valid):
                    content = render_preview(doc, selected, values, states, valid)
                    parsed = ParsedPreview(content); data = json.loads(parsed.json_data)
                    self.assertEqual("SOURCE OBJECTUNKNOWNNATIVE NOT RENDERED", parsed.element_text[0])
                    self.assertIn("unknown source-object", parsed.element_attrs[0]["class"])
                    self.assertEqual([0], data["native_preserved_indexes"])
                    self.assertEqual([], data["invalid_native_preserved_indexes"])
                    self.assertEqual("NOT_RUN", data["native_candidate_presentation"]["native_visual_acceptance"])
                    self.assertNotIn("{Link1}", parsed.element_text[0])
                    self.assertNotIn("ENABLED", parsed.element_text[0])
                    branch = content.split("if(kind==='native_preserved'||kind==='native_presentation'||kind==='native_integer_numeric'||kind==='native_entry_permission'||kind==='native_control_clone'){", 1)[1].split("else if(kind==='button'", 1)[0]
                    self.assertIn("unknown(node,'NATIVE NOT RENDERED')", branch)
                    self.assertNotIn("tagSample", branch)

    def test_invalid_permission_preview_never_recovers_via_samples_or_invents_native_style(self):
        doc = native_entry_permission_design()
        doc["screens"][0]["elements"][0]["entry_permission"]["enable_level"] = True
        content = render_preview(doc, profile(), {"permission": 1})
        parsed = ParsedPreview(content); data = json.loads(parsed.json_data)
        self.assertEqual("SOURCE OBJECT INVALIDUNKNOWNNATIVE NOT RENDERED", parsed.element_text[0])
        self.assertEqual([0], data["invalid_native_preserved_indexes"])
        self.assertIn("font-size:20px;color:#e6edf5;background:#303d4e;", parsed.element_attrs[0]["style"])
        self.assertIn("invalidNativePreserved.has(Number(node.dataset.index))", content)
        doc["screens"][0]["elements"][0].update(width=1, height=1)
        content = render_preview(doc, profile())
        branch = content.split("function fit(node){", 1)[1].split("if(sourcePreservedAlarms", 1)[0]
        self.assertIn("Native rendering remains unqualified", branch)
        self.assertNotIn("fontSize=", branch)
        self.assertNotIn("textContent=", branch)


class ExistingIntegerNumericDesignTests(unittest.TestCase):
    def test_display_contract_and_input_raw_domain_are_distinct(self):
        doc=native_integer_numeric_design();before=copy.deepcopy(doc)
        self.assertEqual(validate_design(doc,profile()),[]);self.assertEqual(doc,before)
        digest=canonical_hash(doc)
        settings=doc['screens'][0]['elements'][0]['integer_numeric']
        settings.update(integer_digits=4,fractional_digits=1)
        self.assertEqual(validate_design(doc,profile()),[]);self.assertNotEqual(canonical_hash(doc),digest)
        settings.update(integer_digits=5,fractional_digits=0,raw_minimum=-32768,raw_maximum=32767)
        self.assertEqual(validate_design(doc,profile()),[])
        settings.update(data_type='UINT',raw_minimum=0,raw_maximum=65535)
        self.assertEqual(validate_design(doc,profile()),[])

    def test_refuses_fractional_input_narrowed_domain_and_malformed_settings(self):
        for change in ({'integer_digits':5},{'fractional_digits':2,'integer_digits':3},
                {'data_type':'LREAL'},{'value_model':'ieee_float'},
                {'integer_digits':True},{'fractional_digits':False},
                {'raw_minimum':0},{'raw_minimum':0,'raw_maximum':100},
                {'raw_minimum':0,'raw_maximum':0,'fractional_digits':0,'integer_digits':5},
                {'raw_minimum':-32769,'raw_maximum':32767,'fractional_digits':0,'integer_digits':5},
                {'raw_minimum':0,'raw_maximum':32767,'fractional_digits':0,'integer_digits':4},
                {'raw_minimum':'0','raw_maximum':100,'fractional_digits':0,'integer_digits':5}):
            doc=native_integer_numeric_design();doc['screens'][0]['elements'][0]['integer_numeric'].update(change)
            with self.subTest(change=change):self.assertTrue(validate_design(doc,profile()))
        for settings in (None,False,[],{}, {'gain':1}):
            doc=native_integer_numeric_design();doc['screens'][0]['elements'][0]['integer_numeric']=settings
            with self.subTest(settings=settings):self.assertTrue(validate_design(doc,profile()))

    def test_capability_and_immutable_source_metadata_are_explicit(self):
        selected=profile();selected['capabilities']['native_integer_numeric']='UNVERIFIED'
        self.assertIn('FEATURE_UNSUPPORTED',codes(native_integer_numeric_design(),selected))
        for change in ({'binding':{'write':'missing'}},{'text':'-3.2768'},{'unit':'degC'},
                {'minimum':0},{'gain':2},{'behavior':'maintained'}, {'samples':[0,-32768]}):
            doc=native_integer_numeric_design();doc['screens'][0]['elements'][0].update(change)
            with self.subTest(change=change):self.assertTrue(validate_design(doc,profile()))

    def test_preview_never_claims_numeric_or_native_glyph_rendering(self):
        doc=native_integer_numeric_design();selected=profile()
        selected['native_schema']={'native_candidate':{'mode':'existing_edit'}}
        content=render_preview(doc,selected);parsed=ParsedPreview(content)
        self.assertEqual(parsed.element_text[0],'SOURCE OBJECTUNKNOWNNATIVE NOT RENDERED')
        self.assertIn("native_integer_numeric",content)
        data=json.loads(parsed.json_data)['native_candidate_presentation']
        self.assertEqual(data['native_visual_acceptance'],'NOT_RUN')
        self.assertNotIn('-3.2768',parsed.element_text[0])


class ExistingPresentationDesignTests(unittest.TestCase):
    def test_pinned_presentation_hashes_intent_without_interpreting_behavior(self):
        doc=native_presentation_design();before=copy.deepcopy(doc)
        self.assertEqual(validate_design(doc,profile()),[]);self.assertEqual(doc,before)
        digest=canonical_hash(doc)
        doc['screens'][0]['elements'][0]['presentation']['states'][0]['surface_color']=2
        self.assertNotEqual(digest,canonical_hash(doc))
        self.assertEqual(validate_design(doc,profile()),[])
        for fields in ({'binding':{'write':'missing'}},{'text':'RUNNING'},{'behavior':'maintained'},
                {'minimum':0,'maximum':100},{'font_size':24},{'target_screen':'overview'}):
            bad=native_presentation_design();bad['screens'][0]['elements'][0].update(fields)
            self.assertTrue(validate_design(bad,profile()))

    def test_native_scalar_domains_and_state_identity_are_exact(self):
        for field,values in [('font_size',[True,0,23,96]),('font_ratio',[False,0,48,151]),
                ('surface_color',[True,-1,0x1000000]),('font_color',[False,-1,0x1000000]),
                ('value',[False,0,'01','-1']),('state_sha256',[None,'A'*64,'a'*63])]:
            for value in values:
                with self.subTest(field=field,value=value):
                    doc=native_presentation_design();doc['screens'][0]['elements'][0]['presentation']['states'][0][field]=value
                    self.assertTrue(validate_design(doc,profile()))
        doc=native_presentation_design();states=doc['screens'][0]['elements'][0]['presentation']['states']
        states.append(copy.deepcopy(states[0]));self.assertIn('NATIVE_PRESENTATION_STATE',codes(doc))
        for value in (None,False,[],{'states':[]},{'visual':{'native_style':True}},
                {'visual':{'native_style':4}},{'numeric_type':'INT'},{'states':[{'value':'0','state_sha256':'b'*64}]}):
            doc=native_presentation_design();doc['screens'][0]['elements'][0]['presentation']=value
            self.assertTrue(validate_design(doc,profile()))
        doc=native_presentation_design();doc['screens'][0]['elements'][0]['presentation']={}
        self.assertEqual(validate_design(doc,profile()),[])

    def test_presentation_and_background_need_separate_explicit_capabilities(self):
        selected=profile();selected['capabilities']['native_presentation']='UNVERIFIED'
        self.assertIn('FEATURE_UNSUPPORTED',codes(native_presentation_design(),selected))
        doc=preserved_native_design();doc['screens'][0]['native_background']={
            'frame_sha256':'a'*64,'asset_path':'assets/opaque.png','asset_sha256':'b'*64}
        self.assertIn('FEATURE_UNSUPPORTED',codes(doc))
        selected=profile();selected['capabilities']['native_background']='OFFLINE_PASS'
        self.assertEqual(validate_design(doc,selected),[])
        for path in ('C:/source.png','../source.png','assets/../source.png','/source.png','\\server\\source.png','a\0.png'):
            bad=copy.deepcopy(doc);bad['screens'][0]['native_background']['asset_path']=path
            self.assertIn('NATIVE_BACKGROUND_PATH',codes(bad,selected))

    def test_declared_png_preview_is_pinned_at_exact_canvas_with_unknown_controls(self):
        from test_existing_edit import page_png
        raw=page_png();doc=native_presentation_design();screen=doc['screens'][0]
        screen.update(width=128,height=96);screen['elements'][0].update(x=2,y=2,width=100,height=40)
        screen['native_background']={'frame_sha256':'a'*64,'asset_path':'assets/p.png','asset_sha256':hashlib.sha256(raw).hexdigest()}
        selected=profile(resolution=[128,96]);selected['capabilities']['native_background']='OFFLINE_PASS'
        selected['native_schema']={'native_candidate':{'mode':'existing_edit'}}
        content=render_preview(doc,selected,background_images={'1':raw});parsed=ParsedPreview(content)
        self.assertEqual(parsed.images,1);self.assertEqual(parsed.element_text[0],'SOURCE OBJECTUNKNOWNNATIVE NOT RENDERED')
        self.assertIn('width="128" height="96"',content);self.assertIn('BACKGROUND ONLY',content)
        data=json.loads(parsed.json_data)
        self.assertEqual(data['native_candidate_presentation']['policy'],'REQUESTED_BACKGROUND_ONLY_CONTROLS_NOT_RENDERED')
        self.assertEqual(data['native_candidate_presentation']['native_visual_acceptance'],'NOT_RUN')
        self.assertLess(content.index('data-native-background='),content.index('data-index="0"'))
        for assets in ({},{'1':raw,'7':raw},{'7':raw},{'1':b'changed'},False):
            with self.subTest(assets=type(assets).__name__),self.assertRaises(HmiError):render_preview(doc,selected,background_images=assets)

    def test_declared_background_cannot_be_silently_omitted_or_supplied_as_none(self):
        doc=native_presentation_design()
        doc['screens'][0]['native_background']={'frame_sha256':'a'*64,
            'asset_path':'assets/p.png','asset_sha256':'b'*64}
        selected=profile();selected['capabilities']['native_background']='OFFLINE_PASS'
        selected['native_schema']={'native_candidate':{'mode':'existing_edit'}}
        for assets in (None,{'1':None},{'1':bytearray(b'png')},{'1':'png'}):
            with self.subTest(assets=assets),self.assertRaises(HmiError) as failure:
                render_preview(doc,selected,background_images=assets)
            self.assertEqual(failure.exception.code,'PREVIEW_BACKGROUND')

    def test_geometry_only_preview_truthfully_reports_no_background_requested(self):
        doc=native_presentation_design();doc['screens'][0]['elements'][0]['presentation']={}
        selected=profile();selected['native_schema']={'native_candidate':{'mode':'existing_edit'}}
        for assets in (None,{}):
            with self.subTest(assets=assets):
                content=render_preview(doc,selected,background_images=assets)
                parsed=ParsedPreview(content)
                self.assertEqual(parsed.images,0)
                self.assertIn('NO BACKGROUND REQUESTED',content)
                self.assertIn('source background is not rendered',content)
                self.assertNotIn('pinned requested opaque PNG is shown',content)
                data=json.loads(parsed.json_data)['native_candidate_presentation']
                self.assertEqual(data['policy'],'NO_BACKGROUND_REQUESTED_CONTROLS_NOT_RENDERED')
                self.assertEqual(data['native_visual_acceptance'],'NOT_RUN')

    def test_cli_missing_background_refuses_before_output_or_parent_publication(self):
        import contextlib
        import io
        import tempfile
        from unittest.mock import patch
        from universal_hmi.cli import main
        doc=native_presentation_design()
        doc['screens'][0]['native_background']={'frame_sha256':'a'*64,
            'asset_path':'assets/p.png','asset_sha256':'b'*64}
        selected=profile();selected['capabilities']['native_background']='OFFLINE_PASS'
        selected['native_schema']={'native_candidate':{'mode':'existing_edit'}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);registry=root/'registry';registry.mkdir()
            source=root/'design.json';source.write_text(json.dumps(doc),encoding='utf-8')
            (registry/'synthetic_dopsoft2.json').write_text(json.dumps(selected),encoding='utf-8')
            original=source.read_bytes();output=root/'not_created'/'preview.html'
            argv=['uhmi','--profiles',str(registry),'preview',str(source),'synthetic_dopsoft2',str(output)]
            stderr=io.StringIO()
            with patch('sys.argv',argv),contextlib.redirect_stderr(stderr),self.assertRaises(SystemExit) as failure:
                main()
            self.assertEqual(failure.exception.code,2)
            self.assertIn('PREVIEW_BACKGROUND',stderr.getvalue())
            self.assertFalse(output.parent.exists());self.assertEqual(source.read_bytes(),original)
            del doc['screens'][0]['native_background']
            source.write_text(json.dumps(doc),encoding='utf-8')
            with patch('sys.argv',argv),contextlib.redirect_stdout(io.StringIO()):main()
            self.assertIn('NO BACKGROUND REQUESTED',output.read_text(encoding='utf-8'))


class ParsedPreview(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.current_element = None
        self.depth = 0
        self.element_text = {}
        self.element_attrs = {}
        self.script_id = None
        self.json_data = ""
        self.scripts = 0
        self.images = 0
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.scripts += 1
            self.script_id = attrs.get("id")
        if tag == "img":
            self.images += 1
        if self.current_element is not None:
            self.depth += 1
        elif "data-index" in attrs:
            self.current_element = int(attrs["data-index"])
            self.depth = 1
            self.element_text[self.current_element] = ""
            self.element_attrs[self.current_element] = attrs

    def handle_endtag(self, tag):
        if tag == "script":
            self.script_id = None
        if self.current_element is not None:
            self.depth -= 1
            if self.depth == 0:
                self.current_element = None

    def handle_data(self, value):
        if self.current_element is not None:
            self.element_text[self.current_element] += value
        if self.script_id == "preview-data":
            self.json_data += value


class DesignValidationTests(unittest.TestCase):
    def test_native_preserved_is_explicit_hashed_retention_without_semantics(self):
        doc = preserved_native_design(); before = copy.deepcopy(doc)
        self.assertEqual([], validate_design(doc, profile()))
        self.assertEqual(doc, before)
        digest = canonical_hash(doc)
        doc["screens"][0]["elements"][0]["source_owner_sha256"] = "a" * 64
        self.assertNotEqual(digest, canonical_hash(doc))
        self.assertEqual([], validate_design(doc, profile()))
        # This common model cannot attest that a supplied fingerprint belongs
        # to a native file; the immutable source/candidate service gate must.
        self.assertEqual([], doc["tags"])
        self.assertEqual([], doc["macros"])

    def test_native_preserved_requires_all_fields_exact_identity_and_hash(self):
        for key in ("native_id", "source_owner_sha256", "text", "x", "width"):
            with self.subTest(missing=key):
                doc = preserved_native_design(); del doc["screens"][0]["elements"][0][key]
                self.assertIn("NATIVE_PRESERVED_FIELDS", codes(doc))
        for value in (None, False, 0, 1.0, [], {}, "01", "-1", "2147483648", "1\n", " "):
            with self.subTest(native_id=value):
                doc = preserved_native_design(); doc["screens"][0]["elements"][0]["native_id"] = value
                self.assertIn("NATIVE_PRESERVED_ID", codes(doc))
        for value in (None, True, 64, [], {}, "a" * 63, "a" * 65, "A" * 64, "g" * 64, "a" * 64 + "\n"):
            with self.subTest(hash=value):
                doc = preserved_native_design(); doc["screens"][0]["elements"][0]["source_owner_sha256"] = value
                self.assertIn("NATIVE_PRESERVED_HASH", codes(doc))
        for value in (None, False, 0, [], {}, "SOURCE", " "):
            with self.subTest(text=value):
                doc = preserved_native_design(); doc["screens"][0]["elements"][0]["text"] = value
                self.assertIn("NATIVE_PRESERVED_TEXT", codes(doc))

    def test_native_preserved_has_no_style_binding_action_or_numeric_override(self):
        overrides = {"font_size": 24, "color": "#ffffff", "fill": "#ff0000", "states": [], "binding": {},
                     "behavior": "momentary", "role": "feedback", "unit": "", "unit_label": "source_object",
                     "minimum": 0, "maximum": 1, "fractional": 0, "format": "decimal", "target_screen": "missing",
                     "view_policy": "preserve_source", "native_type": "6", "columns": [], "sourceOwnerSHA256": "a" * 64}
        for key, value in overrides.items():
            with self.subTest(key=key):
                doc = preserved_native_design(); doc["screens"][0]["elements"][0][key] = value
                self.assertIn("NATIVE_PRESERVED_PROPERTY", codes(doc))
        doc = preserved_native_design(); doc["screens"][0]["elements"][0].update(
            binding={"write": "missing"}, target_screen="missing")
        findings = codes(doc)
        self.assertIn("NATIVE_PRESERVED_PROPERTY", findings)
        self.assertNotIn("UNKNOWN_TAG", findings)
        self.assertNotIn("NAVIGATION_TARGET", findings)

    def test_source_owner_hash_has_only_native_preserved_element_scope(self):
        for owner in (lambda d: d, lambda d: d["screens"][0]):
            doc = preserved_native_design(); owner(doc)["source_owner_sha256"] = "a" * 64
            self.assertIn("UNKNOWN_PROPERTY", codes(doc))
        for kind in KINDS - {"native_preserved", "native_presentation", "native_integer_numeric", "native_entry_permission", "native_control_clone"}:
            with self.subTest(kind=kind):
                doc = preserved_native_design(); doc["screens"][0]["elements"][0]["kind"] = kind
                self.assertIn("KIND_PROPERTY", codes(doc))

    def test_native_preserved_capability_does_not_expand_other_support(self):
        for status in ("OFFLINE_PASS", {"status": "OFFLINE_PASS"}, "SYNTHETIC_ONLY", {"status": "SYNTHETIC_ONLY"}):
            with self.subTest(status=status):
                selected = profile(); selected["capabilities"]["native_preserved"] = status
                self.assertEqual([], validate_design(preserved_native_design(), selected))
        for status in (None, True, [], {}, "UNVERIFIED", "UNSUPPORTED", "SUPPORTED"):
            with self.subTest(status=status):
                selected = profile(); selected["capabilities"]["native_preserved"] = status
                self.assertIn("FEATURE_UNSUPPORTED", codes(preserved_native_design(), selected))
        selected = profile(); selected["fixture_kind"] = "vendor"
        selected["capabilities"]["native_preserved"] = "SYNTHETIC_ONLY"
        self.assertIn("FEATURE_UNSUPPORTED", codes(preserved_native_design(), selected))
        selected = profile(); selected["capabilities"]["button"] = "SYNTHETIC_ONLY"
        self.assertIn("FEATURE_UNSUPPORTED", codes(design(), selected))

    def test_native_preserved_keeps_identity_and_geometry_validation(self):
        for update, expected in (({"x": -1}, "ELEMENT_GEOMETRY"), ({"x": 1.0}, "ELEMENT_GEOMETRY"),
                                 ({"y": True}, "ELEMENT_GEOMETRY"), ({"width": 0}, "ELEMENT_GEOMETRY"),
                                 ({"height": float("inf")}, "ELEMENT_GEOMETRY"), ({"x": 799}, "ELEMENT_OUTSIDE_SCREEN"),
                                 ({"id": []}, "INVALID_ID"), ({"id": " source"}, "INVALID_ID")):
            with self.subTest(update=update):
                doc = preserved_native_design(); doc["screens"][0]["elements"][0].update(update)
                self.assertIn(expected, codes(doc))

    def test_alarm_preserve_source_policy_is_explicit_for_each_view_and_hashed(self):
        for kind in ("alarm_strip", "alarm_table", "alarm_history"):
            with self.subTest(kind=kind):
                doc = preserved_alarm_design(kind)
                before = copy.deepcopy(doc)
                self.assertEqual([], validate_design(doc, profile()))
                self.assertEqual(before, doc)
                digest = canonical_hash(doc)
                del doc["screens"][0]["elements"][0]["view_policy"]
                self.assertEqual([], validate_design(doc, profile()))
                self.assertNotEqual(digest, canonical_hash(doc))
                digest = canonical_hash(doc)
                doc["alarms"][0]["history_policy"] = "retain"
                self.assertNotEqual(digest, canonical_hash(doc))

    def test_alarm_history_policy_preserves_legacy_conceptual_choices(self):
        for policy in ("retain", "clear", "preserve_source"):
            with self.subTest(policy=policy):
                doc = preserved_alarm_design()
                doc["alarms"][0]["history_policy"] = policy
                self.assertEqual([], validate_design(doc, profile()))
        for policy in (None, False, 0, [], {}, "", " preserve_source", "preserve_source ", "PRESERVE_SOURCE", "reset"):
            with self.subTest(policy=policy):
                doc = preserved_alarm_design()
                doc["alarms"][0]["history_policy"] = policy
                self.assertIn("ALARM_HISTORY_POLICY", codes(doc))

    def test_alarm_view_policy_rejects_wrong_types_and_unknown_or_inexact_values(self):
        for kind in ("alarm_strip", "alarm_table", "alarm_history"):
            for policy in (None, True, 1, [], {}, "", "retain", "clear", "preserve_source ", " preserve_source", "PRESERVE_SOURCE"):
                with self.subTest(kind=kind, policy=policy):
                    doc = preserved_alarm_design(kind)
                    doc["screens"][0]["elements"][0]["view_policy"] = policy
                    self.assertIn("ALARM_VIEW_POLICY", codes(doc))

    def test_alarm_source_preserved_view_requires_explicit_empty_text(self):
        for text in (None, [], {}, 0, False, " ", "\x00", "ALARMS"):
            with self.subTest(text=text):
                doc = preserved_alarm_design()
                doc["screens"][0]["elements"][0]["text"] = text
                self.assertIn("ALARM_VIEW_TEXT", codes(doc))
        doc = preserved_alarm_design(); del doc["screens"][0]["elements"][0]["text"]
        self.assertIn("ALARM_VIEW_TEXT", codes(doc))

    def test_alarm_source_preserved_view_cannot_override_native_presentation_or_behavior(self):
        overrides = {"font_size": 20, "color": "#fff", "fill": "#000", "binding": {}, "states": [],
                     "behavior": "maintained", "unit": "", "unit_label": "fault_heading", "minimum": 0,
                     "maximum": 1, "fractional": 0, "format": "decimal", "target_screen": "overview", "role": "feedback"}
        for kind in ("alarm_strip", "alarm_table", "alarm_history"):
            for key, value in overrides.items():
                with self.subTest(kind=kind, key=key):
                    doc = preserved_alarm_design(kind)
                    doc["screens"][0]["elements"][0][key] = value
                    findings = validate_design(doc, profile())
                    self.assertTrue(any(issue["code"] == "ALARM_VIEW_PROPERTY" and key in issue["message"]
                                        and issue.get("element_id") == "fault_view" for issue in findings))

    def test_alarm_view_policy_has_exact_ir_owner_and_no_unknown_keys(self):
        for kind in ("text", "button", "indicator", "numeric_input", "numeric_display", "goto"):
            with self.subTest(kind=kind):
                doc = preserved_alarm_design(); doc["screens"][0]["elements"][0]["kind"] = kind
                self.assertIn("KIND_PROPERTY", codes(doc))
        for owner in (lambda doc: doc, lambda doc: doc["screens"][0], lambda doc: doc["tags"][0], lambda doc: doc["alarms"][0]):
            doc = preserved_alarm_design(); owner(doc)["view_policy"] = "preserve_source"
            self.assertIn("UNKNOWN_PROPERTY", codes(doc))
        for key in ("columns", "timestamp", "history_storage", "acknowledge", "viewPolicy"):
            with self.subTest(key=key):
                doc = preserved_alarm_design(); doc["screens"][0]["elements"][0][key] = []
                self.assertIn("UNKNOWN_PROPERTY", codes(doc))

    def test_every_alarm_view_requires_declared_alarms_even_for_legacy_preview(self):
        for kind in ("alarm_strip", "alarm_table", "alarm_history"):
            for legacy in (False, True):
                for alarms in ([], None, {}):
                    with self.subTest(kind=kind, legacy=legacy, alarms=alarms):
                        doc = preserved_alarm_design(kind); doc["alarms"] = alarms
                        if legacy:
                            del doc["screens"][0]["elements"][0]["view_policy"]
                        findings = validate_design(doc, profile())
                        self.assertTrue(any(issue["code"] == "ALARM_VIEW_ALARMS" and issue.get("element_id") == "fault_view" for issue in findings))
        for alarms in ([None], [[]], [{}]):
            with self.subTest(alarms=alarms):
                doc = preserved_alarm_design(); doc["alarms"] = alarms
                self.assertTrue(validate_design(doc, profile()))

    def test_alarm_preservation_keeps_profile_and_geometry_gates(self):
        doc = preserved_alarm_design(); selected = profile(); selected["capabilities"]["alarm_strip"] = "UNVERIFIED"
        self.assertIn("FEATURE_UNSUPPORTED", codes(doc, selected))
        doc["screens"][0]["elements"][0]["x"] = -1
        self.assertIn("ELEMENT_GEOMETRY", codes(doc))
        doc["screens"][0]["elements"][0].update(x=799, width=600)
        self.assertIn("ELEMENT_OUTSIDE_SCREEN", codes(doc))

    def test_examples_fit_exact_synthetic_resolutions(self):
        cases = [("neutral_800x480.json", "synthetic_dopsoft2", [800, 480]),
                 ("neutral_1024x600.json", "synthetic_diascreen", [1024, 600]),
                 ("synthetic_dopsoft2_design.json", "synthetic_dopsoft2", [800, 480]),
                 ("synthetic_diascreen_design.json", "synthetic_diascreen", [1024, 600])]
        for filename, pid, resolution in cases:
            with self.subTest(fixture=filename):
                fixture = json.loads((ROOT / "examples" / filename).read_text(encoding="utf-8"))
                self.assertEqual([], validate_design(fixture, profile(pid, resolution)))

    def test_hash_uses_exact_sorted_utf8_finite_json(self):
        value = {"é": "sıcaklık", "a": [1, 2]}
        expected = hashlib.sha256('{"a":[1,2],"é":"sıcaklık"}'.encode("utf-8")).hexdigest()
        self.assertEqual(expected, canonical_hash(value))
        self.assertEqual(expected, canonical_hash({"a": [1, 2], "é": "sıcaklık"}))
        for invalid in (float("nan"), float("inf"), {"x": object()}):
            with self.subTest(value=type(invalid).__name__), self.assertRaises(HmiError):
                canonical_hash(invalid)

    def test_new_project_never_invents_screen_or_tag(self):
        self.assertEqual([], new_project("pilot", "profile")["tags"])
        self.assertEqual([], new_project("pilot", "profile")["screens"])
        self.assertIn("NO_SCREENS", codes(new_project("pilot", "synthetic_dopsoft2")))
        with self.assertRaises(HmiError):
            new_project(" pilot", "profile")

    def test_address_and_identifier_collisions_are_rejected(self):
        doc = design()
        second = copy.deepcopy(doc["tags"][0]); second["id"] = "second_request"
        doc["tags"].append(second)
        self.assertIn("DUPLICATE_ADDRESS", codes(doc))
        second["address"] = "DEMO.SECOND"
        second["id"] = "run_button"
        self.assertIn("DUPLICATE_ID", codes(doc))

    def test_distinct_declared_station_is_not_collapsed(self):
        doc = design()
        second = copy.deepcopy(doc["tags"][0]); second.update(id="second_request", station="SECOND")
        doc["tags"].append(second)
        self.assertNotIn("DUPLICATE_ADDRESS", codes(doc))

    def test_binding_must_exactly_match_and_cannot_write_readonly(self):
        doc = design(); elements = doc["screens"][0]["elements"]
        elements[5]["binding"]["write"] = "run_feedback"
        self.assertIn("READ_ONLY_WRITE", codes(doc))
        elements[5]["binding"]["write"] = "run_request "
        self.assertIn("UNKNOWN_TAG", codes(doc))

    def test_bool_behavior_and_states_do_not_silently_change(self):
        for change, expected in (({"behavior": "toggle"}, "BUTTON_BEHAVIOR"),
                                 ({"states": [{"value": 0, "text": "Only off", "fill": "#000000"}]}, "BOOL_STATES"),
                                 ({"states": [{"value": False, "text": "Off", "fill": "#000000"}, {"value": True, "text": "On", "fill": "#00ff00"}]}, "BOOL_STATES")):
            with self.subTest(change=change):
                doc = design(); doc["screens"][0]["elements"][5].update(change)
                self.assertIn(expected, codes(doc))

    def test_command_bit_cannot_be_physical_feedback(self):
        doc = design(); doc["screens"][0]["elements"][1]["binding"]["read"] = "run_request"
        self.assertIn("COMMAND_AS_FEEDBACK", codes(doc))
        doc["screens"][0]["elements"][1]["role"] = "request"
        self.assertNotIn("COMMAND_AS_FEEDBACK", codes(doc))

    def test_input_numeric_range_precision_and_units_are_exact(self):
        for tag_type, updates, expected in (
            ("UINT", {"maximum": 65536}, "NUMERIC_LIMIT"),
            ("DINT", {"minimum": -2147483649}, "NUMERIC_LIMIT"),
            ("UDINT", {"maximum": 4294967296}, "NUMERIC_LIMIT"),
            ("INT", {"fractional": 1}, "NUMERIC_PRECISION"),
            ("REAL", {"fractional": 8}, "NUMERIC_PRECISION"),
            ("LREAL", {"fractional": 16}, "NUMERIC_PRECISION"),
            ("REAL", {"minimum": 3, "maximum": 2}, "NUMERIC_LIMIT_ORDER"),
            ("REAL", {"unit": "Hz"}, "UNIT_MISMATCH"),
            ("REAL", {"maximum": float("inf")}, "NUMERIC_LIMIT"),
            ("REAL", {"maximum": 10**400}, "NUMERIC_LIMIT")):
            with self.subTest(tag_type=tag_type, updates=updates):
                doc = design(); doc["tags"][4]["data_type"] = tag_type
                doc["screens"][0]["elements"][3].update(updates)
                self.assertIn(expected, codes(doc))

    def test_integer_boundaries_remain_integer_no_narrowing(self):
        doc = design(); doc["tags"][4]["data_type"] = "UDINT"
        doc["screens"][0]["elements"][3].update(minimum=0, maximum=4294967295, fractional=0)
        self.assertEqual([], validate_design(doc, profile()))
        doc["screens"][0]["elements"][3]["maximum"] = 4294967295.0
        self.assertIn("NUMERIC_LIMIT", codes(doc))

    def test_time_requires_profile_support_and_never_becomes_int(self):
        doc = design(); doc["tags"][4].update(data_type="TIME", unit="ms")
        doc["screens"][0]["elements"][3].update(unit="ms", fractional=0)
        self.assertIn("NUMERIC_TYPE_UNSUPPORTED", codes(doc))
        selected = profile(); selected["numeric_types"].append("TIME")
        self.assertEqual([], validate_design(doc, selected))
        self.assertEqual("TIME", doc["tags"][4]["data_type"])

    def test_geometry_navigation_and_text_owner_are_gates(self):
        for updates, expected in (({"x": -1}, "ELEMENT_GEOMETRY"), ({"width": 0}, "ELEMENT_GEOMETRY"),
                                  ({"x": 1.5}, "ELEMENT_GEOMETRY"), ({"x": 799}, "ELEMENT_OUTSIDE_SCREEN"),
                                  ({"y": 20}, "TEXT_OVERLAP")):
            with self.subTest(updates=updates):
                doc = design(); doc["screens"][0]["elements"][1].update(updates)
                self.assertIn(expected, codes(doc))
        doc = design(); doc["screens"][0]["elements"].append({"id": "nav", "kind": "goto", "x": 720, "y": 20, "width": 40, "height": 30, "target_screen": "missing"})
        self.assertIn("NAVIGATION_TARGET", codes(doc))

    def test_profile_unknown_features_never_pass_native_gate(self):
        for status in ("UNVERIFIED", "UNSUPPORTED", "SUPPORTED", None):
            with self.subTest(status=status):
                selected = profile(); selected["capabilities"]["button"] = status
                self.assertIn("FEATURE_UNSUPPORTED", codes(design(), selected))

    def test_macro_unknown_trigger_operation_and_readonly_are_explicit(self):
        doc = design(); doc["macros"] = [{"id": "startup_macro", "trigger": "startup", "statements": [{"op": "bit_on", "tag": "run_request"}]}]
        self.assertEqual([], validate_design(doc, profile()))
        doc["macros"][0]["trigger"] = "after_download"
        self.assertIn("MACRO_TRIGGER", codes(doc))
        doc["macros"][0]["statements"][0] = {"op": "force", "tag": "run_request"}
        self.assertIn("MACRO_OP", codes(doc))
        doc["macros"][0]["statements"][0] = {"op": "bit_on", "tag": "run_feedback"}
        self.assertIn("MACRO_READ_ONLY_WRITE", codes(doc))

    def test_macro_if_preserves_exact_operand_types(self):
        doc = design(); doc["macros"] = [{"id": "condition", "trigger": "clock", "statements": [{"op": "if", "tag": "run_feedback", "value": 1, "comparison": "eq", "then": [{"op": "assign", "tag": "speed_setpoint", "value": 120.5}]}]}]
        self.assertEqual([], validate_design(doc, profile()))
        doc["macros"][0]["statements"][0]["value"] = 2
        self.assertIn("MACRO_VALUE", codes(doc))

    def test_macro_command_is_not_independent_feedback(self):
        doc = design(); doc["tags"][2]["access"] = "ReadWrite"
        doc["macros"] = [{"id": "feedback_writer", "trigger": "button", "statements": [{"op": "bit_on", "tag": "run_feedback"}]}]
        self.assertIn("COMMAND_AS_FEEDBACK", codes(doc))

    def test_malformed_json_shape_returns_issues_instead_of_exception(self):
        doc = design()
        doc["tags"][0]["data_type"] = []
        doc["tags"][0]["access"] = {}
        doc["screens"][0]["elements"][1]["kind"] = []
        doc["screens"][0]["elements"][2]["binding"]["read"] = []
        doc["alarms"][0]["history_policy"] = []
        self.assertGreater(len(validate_design(doc, profile())), 0)

    def test_unknown_semantic_fields_fail_at_every_ir_level(self):
        cases = [
            (lambda doc: doc, "extra_document"),
            (lambda doc: doc["screens"][0], "extra_screen"),
            (lambda doc: doc["screens"][0]["elements"][1], "layer"),
            (lambda doc: doc["screens"][0]["elements"][1], "opacity"),
            (lambda doc: doc["screens"][0]["elements"][1], "image"),
            (lambda doc: doc["screens"][0]["elements"][1]["binding"], "scale"),
            (lambda doc: doc["tags"][0], "converter"),
            (lambda doc: doc["screens"][0]["elements"][1]["states"][0], "animation"),
            (lambda doc: doc["alarms"][0], "acknowledge_macro"),
        ]
        for locate, key in cases:
            with self.subTest(key=key):
                doc = design(); locate(doc)[key] = "unsupported"
                findings = validate_design(doc, profile())
                self.assertTrue(any(issue["code"] == "UNKNOWN_PROPERTY" and key in issue["message"] for issue in findings))
        doc = design(); doc["macros"] = [{"id": "extra_macro", "trigger": "startup", "statements": [{"op": "bit_on", "tag": "run_request", "delay": 10}], "interval": 10}]
        self.assertGreaterEqual(sum(issue["code"] == "UNKNOWN_PROPERTY" for issue in validate_design(doc, profile())), 2)

    def test_known_semantics_cannot_be_ignored_on_another_kind(self):
        for index, key, value in ((0, "states", []), (0, "binding", {"read": "run_request"}),
                                  (1, "behavior", "maintained"), (2, "target_screen", "overview"),
                                  (5, "fractional", 1), (8, "unit", "ms")):
            with self.subTest(index=index, key=key):
                doc = design(); doc["screens"][0]["elements"][index][key] = value
                self.assertIn("KIND_PROPERTY", codes(doc))
        doc = design(); doc["macros"] = [{"id": "wrong_statement", "trigger": "startup", "statements": [{"op": "bit_on", "tag": "run_request", "value": 0}]}]
        self.assertIn("STATEMENT_PROPERTY", codes(doc))

    def test_native_integration_alias_and_metadata_are_exact_typed_values(self):
        doc = design(); doc["screens"][0]["native_id"] = "1"
        doc["screens"][0]["elements"][1]["native_id"] = "2"
        doc["tags"][0]["native_binding"] = {"link": "1", "mem_type": 0}
        self.assertEqual([], validate_design(doc, profile()))
        for value in (True, -1, 2147483648, "01", "1.0", " 1", [], {}):
            with self.subTest(value=value):
                changed = copy.deepcopy(doc); changed["tags"][0]["native_binding"]["link"] = value
                self.assertIn("NATIVE_BINDING_VALUE", codes(changed))
        for value in (1, "01", "-1", "2147483648", "screen", None):
            with self.subTest(native_id=value):
                changed = copy.deepcopy(doc); changed["screens"][0]["native_id"] = value
                self.assertIn("NATIVE_ID", codes(changed))
        doc["tags"][0]["native_binding"]["ignored"] = 7
        self.assertIn("UNKNOWN_PROPERTY", codes(doc))
        del doc["tags"][0]["native_binding"]["mem_type"]
        self.assertIn("NATIVE_BINDING_FIELDS", codes(doc))

    def test_numeric_input_cannot_read_another_process_or_unit(self):
        doc = design()
        doc["tags"][3]["unit"] = "m"
        doc["screens"][0]["elements"][2]["unit"] = "m"
        doc["screens"][0]["elements"][3]["binding"]["read"] = "actual_speed"
        self.assertIn("NUMERIC_UNIT_MISMATCH", codes(doc))
        self.assertIn("NUMERIC_PROCESS_MISMATCH", codes(doc))
        doc["tags"][3]["unit"] = "rpm"
        doc["screens"][0]["elements"][2]["unit"] = "rpm"
        self.assertIn("NUMERIC_PROCESS_MISMATCH", codes(doc))
        doc["screens"][0]["elements"][3]["binding"]["read"] = None
        self.assertIn("NUMERIC_INPUT_READ", codes(doc))

    def test_boolean_identical_text_and_equivalent_fill_are_ambiguous(self):
        for index in (1, 5):
            with self.subTest(index=index):
                doc = design(); states = doc["screens"][0]["elements"][index]["states"]
                states[0].update(text=" Ready ", fill="#abc")
                states[1].update(text="ready", fill="#aabbccff")
                self.assertIn("BOOL_STATE_AMBIGUOUS", codes(doc))
                states[1]["text"] = "Active"
                self.assertNotIn("BOOL_STATE_AMBIGUOUS", codes(doc))
                states[1].update(text="ready", fill="#336699")
                self.assertNotIn("BOOL_STATE_AMBIGUOUS", codes(doc))

    def test_explicit_unit_label_is_same_page_order_independent_and_hashed(self):
        for kind in ("numeric_input", "numeric_display"):
            with self.subTest(kind=kind):
                doc = unit_label_design(kind)
                self.assertEqual([], validate_design(doc, profile()))
                doc["screens"][0]["elements"].reverse()
                self.assertEqual([], validate_design(doc, profile()))
                before = canonical_hash(doc)
                numeric = doc["screens"][0]["elements"][1]
                del numeric["unit_label"]
                self.assertNotEqual(before, canonical_hash(doc))

    def test_unit_label_malformed_and_unresolvable_references_fail_closed(self):
        for kind in ("numeric_input", "numeric_display"):
            for reference in (None, True, 1, [], {}, "", " unit_owner", "missing", "numeric_owner", "process_value"):
                with self.subTest(kind=kind, reference=reference):
                    doc = unit_label_design(kind)
                    doc["screens"][0]["elements"][0]["unit_label"] = reference
                    self.assertIn("UNIT_LABEL_REFERENCE", codes(doc))

    def test_unit_label_cross_page_duplicate_and_shared_owners_are_rejected(self):
        doc = unit_label_design()
        label = doc["screens"][0]["elements"].pop()
        doc["screens"].append({"id": "second", "name": "Second", "width": 800, "height": 480, "elements": [label]})
        self.assertIn("UNIT_LABEL_SCREEN", codes(doc))
        doc = unit_label_design()
        label = copy.deepcopy(doc["screens"][0]["elements"][1]); label["y"] = 180
        doc["screens"][0]["elements"].append(label)
        self.assertIn("DUPLICATE_ID", codes(doc))
        self.assertIn("UNIT_LABEL_REFERENCE", codes(doc))
        doc = unit_label_design()
        owner = copy.deepcopy(doc["screens"][0]["elements"][0]); owner.update(id="second_numeric", y=180)
        doc["screens"][0]["elements"].append(owner)
        owner_issues = [issue for issue in validate_design(doc, profile()) if issue["code"] == "UNIT_LABEL_OWNER"]
        self.assertEqual({"numeric_owner", "second_numeric"}, {issue["element_id"] for issue in owner_issues})

    def test_unit_label_requires_explicit_exact_nonempty_units_and_literal_text(self):
        for kind in ("numeric_input", "numeric_display"):
            for unit in (None, "", " ", "Hz"):
                with self.subTest(kind=kind, unit=unit):
                    doc = unit_label_design(kind)
                    numeric = doc["screens"][0]["elements"][0]
                    if unit is None:
                        del numeric["unit"]
                    else:
                        numeric["unit"] = unit
                    self.assertIn("UNIT_LABEL_UNIT", codes(doc))
            for text in ("RPM", " rpm", "rpm ", "Hz", None, []):
                with self.subTest(kind=kind, text=text):
                    doc = unit_label_design(kind)
                    doc["screens"][0]["elements"][1]["text"] = text
                    self.assertIn("UNIT_LABEL_TEXT", codes(doc))
            doc = unit_label_design(kind); doc["tags"][0]["unit"] = "Hz"
            self.assertIn("UNIT_LABEL_UNIT", codes(doc))
            self.assertIn("UNIT_MISMATCH", codes(doc))

    def test_unit_label_cannot_own_bound_state_or_reference_chains(self):
        for extra in ({"binding": {}}, {"binding": {"read": "process_value"}},
                      {"unit_label": "numeric_owner"}, {"unit_label": "unit_owner"}):
            with self.subTest(extra=extra):
                doc = unit_label_design(); doc["screens"][0]["elements"][1].update(extra)
                self.assertIn("UNIT_LABEL_BINDING", codes(doc))
                self.assertIn("KIND_PROPERTY", codes(doc))
        doc = unit_label_design(); doc["screens"][0]["elements"][1]["kind"] = "numeric_display"
        self.assertIn("UNIT_LABEL_KIND", codes(doc))
        doc = unit_label_design(); doc["screens"][0]["elements"][1]["states"] = []
        self.assertIn("KIND_PROPERTY", codes(doc))

    def test_unit_label_declares_placement_font_and_colors_and_uses_existing_layout_gates(self):
        for key in ("x", "y", "width", "height", "font_size", "color", "fill"):
            with self.subTest(missing=key):
                doc = unit_label_design(); del doc["screens"][0]["elements"][1][key]
                self.assertIn("UNIT_LABEL_STYLE", codes(doc))
        for change, expected in (({"x": 790}, "ELEMENT_OUTSIDE_SCREEN"), ({"x": 190}, "TEXT_OVERLAP"),
                                 ({"font_size": 5}, "FONT_SIZE"), ({"color": "red"}, "ELEMENT_COLOR")):
            with self.subTest(change=change):
                doc = unit_label_design(); doc["screens"][0]["elements"][1].update(change)
                self.assertIn(expected, codes(doc))


class PreviewTests(unittest.TestCase):
    def test_native_candidate_text_shows_intent_and_disclaims_retained_source_pixels_for_all_statuses(self):
        for status in ("OFFLINE_PASS", "VENDOR_PASS", "PHYSICAL_PASS", "UNVERIFIED", None):
            for spec in (None, False, [], {"qualified": True, "mode": "existing_owner_candidate"}):
                with self.subTest(status=status, spec=spec):
                    doc = preserved_native_design()
                    doc["screens"][0]["elements"].append({"id": "editable_literal", "native_id": "18", "kind": "text",
                        "x": 400, "y": 20, "width": 320, "height": 100, "text": "Yeni başlık"})
                    selected = profile(); selected["fixture_kind"] = "vendor"
                    selected["capabilities"]["text"] = status
                    selected["native_schema"] = {"native_candidate": spec}
                    content = render_preview(doc, selected, valid=False)
                    parsed = ParsedPreview(content); data = json.loads(parsed.json_data)
                    self.assertIn('class="native-candidate-note" role="note"', content)
                    self.assertIn("Native editing retains existing source appearance; native appearance is not rendered here", content)
                    self.assertIn("Browser fonts, colors, backgrounds and fitting do not represent the retained native glyphs or pixels", content)
                    self.assertIn("does not attest calibration, vendor or panel acceptance", content)
                    self.assertEqual("Yeni başlık", parsed.element_text[1])
                    self.assertEqual("text-intent-only", parsed.element_attrs[1]["data-native-presentation"])
                    self.assertIn("font-size:20px;", parsed.element_attrs[1]["style"])
                    self.assertEqual("SOURCE OBJECTUNKNOWNNATIVE NOT RENDERED", parsed.element_text[0])
                    self.assertEqual({"policy": "RETAIN_SOURCE_APPEARANCE", "render_kind": "CONCEPTUAL_IR",
                                      "native_visual_acceptance": "NOT_RUN", "text_intent_indexes": [1]},
                                     data["native_candidate_presentation"])
                    self.assertEqual(0, parsed.images)

    def test_native_candidate_presentation_notice_is_absent_without_the_contract_key(self):
        for schema in (None, [], {}, {"qualified": True}):
            with self.subTest(schema=schema):
                selected = profile()
                if schema is not None:
                    selected["native_schema"] = schema
                content = render_preview(preserved_native_design(), selected)
                parsed = ParsedPreview(content); data = json.loads(parsed.json_data)
                self.assertNotIn('class="native-candidate-note"', content)
                self.assertNotIn("native_candidate_presentation", data)
                self.assertTrue(all("data-native-presentation" not in attributes for attributes in parsed.element_attrs.values()))

    def test_native_preserved_preview_is_unknown_not_a_feature_simulation(self):
        for values, states, valid in (({}, {}, True), ({"sample": 0}, {}, True), ({"sample": 1}, {}, True),
                                     ({"sample": 1}, {"sample": "stale"}, True), ({"sample": 1}, {}, False)):
            with self.subTest(values=values, states=states, valid=valid):
                doc = preserved_native_design()
                doc["tags"] = [{"id": "sample", "address": "DEMO.STATE", "data_type": "BOOL", "access": "Read"}]
                content = render_preview(doc, profile(), values, states, valid)
                parsed = ParsedPreview(content); data = json.loads(parsed.json_data)
                self.assertEqual("SOURCE OBJECTUNKNOWNNATIVE NOT RENDERED", parsed.element_text[0])
                self.assertIn("native_preserved unknown source-object", parsed.element_attrs[0]["class"])
                self.assertNotIn("active", parsed.element_attrs[0]["class"])
                self.assertEqual([0], data["native_preserved_indexes"])
                self.assertEqual([], data["invalid_native_preserved_indexes"])
                self.assertEqual(1, data["native_preserved_count"])
                self.assertIn("retention only, not feature emission", content)
                self.assertIn("Native appearance, addresses and actions are neither rendered nor qualified here", content)
                self.assertNotIn("NAVIGATION ILLUSTRATION", parsed.element_text[0])
                branch = content.split("if(kind==='native_preserved'||kind==='native_presentation'||kind==='native_integer_numeric'||kind==='native_entry_permission'||kind==='native_control_clone'){", 1)[1].split("else if(kind==='button'", 1)[0]
                self.assertNotIn("tagSample", branch)
                self.assertIn("unknown(node,'NATIVE NOT RENDERED');fit(node);return;", branch)

    def test_invalid_native_preserved_preview_uses_stable_indexes_and_fixed_placeholder(self):
        for identifier in ("source\r\nobject", "source\x00object"):
            for override in ({"source_owner_sha256": []}, {"font_size": 96, "color": "#ff0000", "fill": "#00ff00"},
                             {"binding": {"read": "sample", "write": "sample"}}, {"text": "RUNNING"}):
                with self.subTest(identifier=identifier, override=override):
                    doc = preserved_native_design(); doc["screens"][0]["elements"][0].update(id=identifier, **override)
                    content = render_preview(doc, profile(), {"sample": 1})
                    parsed = ParsedPreview(content); data = json.loads(parsed.json_data)
                    self.assertEqual("SOURCE OBJECT INVALIDUNKNOWNNATIVE NOT RENDERED", parsed.element_text[0])
                    self.assertEqual([0], data["invalid_native_preserved_indexes"])
                    self.assertIn("font-size:20px;color:#e6edf5;background:#303d4e;", parsed.element_attrs[0]["style"])
                    self.assertIn("invalidNativePreserved.has(Number(node.dataset.index))", content)
                    self.assertNotIn("invalidNativePreserved.has(node.dataset.elementId)", content)

    def test_native_preserved_placeholder_fit_retains_warning_and_no_native_font_claim(self):
        doc = preserved_native_design(); doc["screens"][0]["elements"][0].update(width=1, height=1)
        content = render_preview(doc, profile())
        parsed = ParsedPreview(content)
        self.assertEqual("SOURCE OBJECTUNKNOWNNATIVE NOT RENDERED", parsed.element_text[0])
        branch = content.split("function fit(node){", 1)[1].split("if(sourcePreservedAlarms", 1)[0]
        self.assertIn("nativePreserved.has(Number(node.dataset.index))", branch)
        self.assertIn("source object placeholder does not fit. Native rendering remains unqualified", branch)
        self.assertNotIn("fontSize=", branch)
        self.assertNotIn("textContent=", branch)

    def test_native_preserved_diagnostic_count_is_separate_from_other_kinds(self):
        doc = preserved_native_design()
        clone = copy.deepcopy(doc["screens"][0]["elements"][0])
        clone.update(id="second_declaration", native_id="18", y=140)
        doc["screens"][0]["elements"].extend([clone, {"id": "heading", "kind": "text", "x": 400, "y": 20,
                                                       "width": 200, "height": 40, "text": "Source inventory"}])
        parsed = ParsedPreview(render_preview(doc, profile()))
        data = json.loads(parsed.json_data)
        self.assertEqual(2, data["native_preserved_count"])
        self.assertEqual([0, 1], data["native_preserved_indexes"])
        self.assertEqual([], data["source_preserved_alarm_indexes"])
        self.assertEqual("Source inventory", parsed.element_text[2])
        self.assertEqual(0, parsed.images)

    def test_source_preserved_alarm_views_are_unqualified_placeholders_for_all_samples(self):
        for kind in ("alarm_strip", "alarm_table", "alarm_history"):
            for values, states, valid in (({}, {}, True), ({"fault": 0}, {}, True), ({"fault": 1}, {}, True),
                                         ({"fault": 1}, {"fault": "stale"}, True), ({"fault": 1}, {}, False)):
                with self.subTest(kind=kind, values=values, states=states, valid=valid):
                    doc = preserved_alarm_design(kind)
                    content = render_preview(doc, profile(), values, states, valid)
                    parsed = ParsedPreview(content)
                    self.assertIn("SOURCE-PRESERVED PRESENTATION", parsed.element_text[0])
                    self.assertIn("UNKNOWN", parsed.element_text[0])
                    self.assertIn("NO HISTORY DATA" if kind == "alarm_history" else "NATIVE VIEW NOT RENDERED", parsed.element_text[0])
                    self.assertNotIn("ACTIVE ALARMS", parsed.element_text[0])
                    self.assertNotIn("Supply fault", parsed.element_text[0])
                    self.assertIn("unknown source-preserved", parsed.element_attrs[0]["class"])
                    self.assertEqual([0], json.loads(parsed.json_data)["source_preserved_alarm_indexes"])
                    self.assertEqual([], json.loads(parsed.json_data)["invalid_alarm_view_indexes"])
                    self.assertIn("Source-native fonts, table columns, timestamps, history storage and actions are neither rendered nor qualified here", content)
                    self.assertEqual("Faults", parsed.element_text[1])

    def test_invalid_source_preserved_view_never_recovers_through_sample_controls(self):
        for change in ({"view_policy": None}, {"view_policy": []}, {"view_policy": {}}, {"view_policy": "retain"},
                       {"text": "ALARMS"}, {"font_size": 32}, {"fill": "#ff0000"}, {"binding": {"read": "fault"}}):
            with self.subTest(change=change):
                doc = preserved_alarm_design(); doc["screens"][0]["elements"][0].update(change)
                content = render_preview(doc, profile(), {"fault": 1})
                parsed = ParsedPreview(content)
                self.assertIn("ALARM VIEW POLICY INVALID", parsed.element_text[0])
                self.assertIn("UNKNOWN", parsed.element_text[0])
                self.assertEqual([0], json.loads(parsed.json_data)["invalid_alarm_view_indexes"])
                self.assertIn("invalidAlarmViews.has(Number(node.dataset.index))", content)
                self.assertIn("if(sourcePreservedAlarms.has(Number(node.dataset.index)))", content)
                self.assertIn("font-size:20px;color:#e6edf5;background:#303d4e;", parsed.element_attrs[0]["style"])
        doc = preserved_alarm_design(); doc["alarms"] = []
        parsed = ParsedPreview(render_preview(doc, profile(), {"fault": 1}))
        self.assertIn("ALARM VIEW POLICY INVALID", parsed.element_text[0])

    def test_source_preserved_placeholder_overflow_does_not_invent_native_fonts_or_drop_history_unknown(self):
        doc = preserved_alarm_design("alarm_history"); doc["screens"][0]["elements"][0].update(width=1, height=1)
        content = render_preview(doc, profile(), {"fault": 1})
        parsed = ParsedPreview(content)
        self.assertIn("UNKNOWN", parsed.element_text[0])
        self.assertIn("NO HISTORY DATA", parsed.element_text[0])
        fit_branch = content.split("function fit(node){", 1)[1].split("if(node.classList.contains('text')", 1)[0]
        self.assertIn("source-preserved presentation placeholder does not fit", fit_branch)
        self.assertNotIn("fontSize=", fit_branch)
        self.assertNotIn("textContent=", fit_branch)

    def test_invalid_alarm_view_indexes_remain_exact_when_html_normalizes_control_ids(self):
        for identifier in ("fault\r\nview", "fault\x00view"):
            with self.subTest(identifier=identifier):
                doc = preserved_alarm_design("alarm_history")
                doc["screens"][0]["elements"][0].update(id=identifier, font_size=30)
                content = render_preview(doc, profile(), {"fault": 1})
                parsed = ParsedPreview(content)
                self.assertIn("ALARM VIEW POLICY INVALID", parsed.element_text[0])
                self.assertEqual([0], json.loads(parsed.json_data)["invalid_alarm_view_indexes"])
                self.assertIn("invalidAlarmViews.has(Number(node.dataset.index))", content)
                self.assertNotIn("invalidAlarmViews.has(node.dataset.elementId)", content)

    def test_legacy_alarm_preview_stays_conceptual_and_history_has_no_fabricated_store(self):
        content = render_preview(design(), profile(), {"alarm_active": 1})
        parsed = ParsedPreview(content)
        self.assertNotIn("SOURCE-PRESERVED PRESENTATION", parsed.element_text[8])
        self.assertNotIn("Source-native fonts, table columns, timestamps, history storage", content)
        self.assertEqual([], json.loads(parsed.json_data)["source_preserved_alarm_indexes"])
        self.assertIn("ACTIVE ALARMS · 1", parsed.element_text[8])
        self.assertIn("alarm retention are not executed here", content)
        doc = preserved_alarm_design("alarm_history"); del doc["screens"][0]["elements"][0]["view_policy"]
        doc["screens"][0]["elements"][0]["text"] = "History"
        for policy in ("retain", "clear", "preserve_source"):
            with self.subTest(policy=policy):
                doc["alarms"][0]["history_policy"] = policy
                parsed = ParsedPreview(render_preview(doc, profile(), {"fault": 1}))
                self.assertIn("HistoryUNKNOWNNO HISTORY DATA", parsed.element_text[0])
                self.assertNotIn("Supply fault", parsed.element_text[0])

    def test_legacy_active_high_bool_alarm_rejects_malformed_samples_and_alarm_records(self):
        for value in (None, False, True, 0.0, 1.0, 2, -1, [], {}, "1"):
            with self.subTest(value=value):
                parsed = ParsedPreview(render_preview(design(), profile(), {"alarm_active": value}))
                self.assertIn("UNKNOWN", parsed.element_text[8])
                self.assertNotIn("ACTIVE ALARMS", parsed.element_text[8])
                self.assertIn("alarm_active", json.loads(parsed.json_data)["invalid_values"])
        self.assertIn("tag.data_type==='BOOL'||Array.isArray(data.numeric[tag.data_type])", render_preview(design(), profile()))
        for alarms in ([None], [[]], [{}], [{"tag": []}], [{"tag": {}}]):
            with self.subTest(alarms=alarms):
                doc = preserved_alarm_design(); del doc["screens"][0]["elements"][0]["view_policy"]
                doc["alarms"] = alarms
                content = render_preview(doc, profile(), {"fault": 1})
                parsed = ParsedPreview(content)
                self.assertIn("UNKNOWN", parsed.element_text[0])
                self.assertIn("ALARM BINDING INVALID", parsed.element_text[0])
                self.assertIn("a&&typeof a==='object'&&!Array.isArray(a)&&typeof a.tag==='string'", content)

    def test_explicit_unit_label_has_one_visual_owner_at_its_own_geometry_and_style(self):
        for kind in ("numeric_input", "numeric_display"):
            for values, states in (({"process_value": 1420.5}, {}), ({}, {}),
                                   ({"process_value": 1420.5}, {"process_value": "stale"})):
                with self.subTest(kind=kind, values=values, states=states):
                    doc = unit_label_design(kind)
                    parsed = ParsedPreview(render_preview(doc, profile(), values, states))
                    self.assertNotIn("rpm", parsed.element_text[0])
                    self.assertEqual("rpm", parsed.element_text[1])
                    self.assertIn("left:240px;top:20px;width:100px;height:50px;font-size:18px;color:#95a9c2;background:#101b2a;",
                                  parsed.element_attrs[1]["style"])
                    self.assertNotIn('<span class="unit">', render_preview(doc, profile(), values, states))
                    data = json.loads(parsed.json_data)
                    self.assertEqual([1], data["unit_label_indexes"])
                    self.assertEqual([], data["invalid_unit_label_indexes"])

    def test_invalid_unit_label_is_unknown_and_cannot_be_restored_as_valid_by_sample_controls(self):
        for reference in (None, True, [], {}, "missing", "numeric_owner"):
            with self.subTest(reference=reference):
                doc = unit_label_design(); doc["screens"][0]["elements"][0]["unit_label"] = reference
                content = render_preview(doc, profile(), {"process_value": 1420.5})
                parsed = ParsedPreview(content)
                self.assertIn("UNKNOWN", parsed.element_text[0])
                self.assertIn("UNIT LABEL INVALID", parsed.element_text[0])
                self.assertIn("UNIT_LABEL_REFERENCE", content)
                self.assertEqual([0], json.loads(parsed.json_data)["invalid_unit_label_indexes"])
                self.assertIn("invalidUnitLabels.has(Number(node.dataset.index))", content)

    def test_linked_unit_label_dom_fit_reports_overflow_without_changing_declared_font(self):
        doc = unit_label_design(); doc["screens"][0]["elements"][1].update(width=1, height=1, font_size=18)
        content = render_preview(doc, profile())
        self.assertIn("unitLabels.has(Number(node.dataset.index))", content)
        self.assertIn("bounds=rangeBounds(label)", content)
        self.assertIn("unit label cannot fit at its declared font size", content)
        self.assertIn("label.textContent='INSUFFICIENT SPACE'", content)
        label_fit = content.split("if(node.classList.contains('text')", 1)[1].split("const value=node.querySelector", 1)[0]
        self.assertNotIn("fontSize=", label_fit)
        self.assertIn("font-size:18px", content)
        self.assertIn("native font and pixel qualification remain separate", content)

    def test_unit_label_fit_uses_stable_indexes_when_html_normalizes_identifier_controls(self):
        for identifier in ("unit\r\nowner", "unit\x00owner"):
            with self.subTest(identifier=identifier):
                doc = unit_label_design()
                doc["screens"][0]["elements"][0]["unit_label"] = identifier
                doc["screens"][0]["elements"][1].update(id=identifier, width=1, height=1)
                self.assertEqual([], validate_design(doc, profile()))
                content = render_preview(doc, profile())
                self.assertEqual([1], json.loads(ParsedPreview(content).json_data)["unit_label_indexes"])
                self.assertIn("unitLabels.has(Number(node.dataset.index))", content)
                self.assertNotIn("unitLabels.has(node.dataset.elementId)", content)

    def test_label_json_text_cannot_inject_markup_or_script(self):
        doc = design(); payload = '</script><script>alert(1)</script><img src=x onerror=alert(2)>'
        doc["screens"][0]["elements"][0]["text"] = payload
        doc["project_id"] = '__DATA__'  # Marker-looking text is ordinary text.
        content = render_preview(doc, profile())
        parsed = ParsedPreview(content)
        self.assertEqual(2, parsed.scripts)
        self.assertEqual(0, parsed.images)
        self.assertEqual(payload, parsed.element_text[0])
        self.assertEqual(payload, json.loads(parsed.json_data)["elements"][0]["text"])
        self.assertIn('<title>__DATA__ · Conceptual HMI preview</title>', content)

    def test_boolean_zero_and_one_use_correct_explicit_state(self):
        for value, label in ((0, "Stopped"), (1, "Running")):
            with self.subTest(value=value):
                parsed = ParsedPreview(render_preview(design(), profile(), values={"run_feedback": value}))
                self.assertIn(label, parsed.element_text[1])
                self.assertNotIn("UNKNOWN", parsed.element_text[1])
                self.assertNotIn("unknown", parsed.element_attrs[1]["class"])

    def test_invalid_stale_missing_and_invalid_bool_are_never_off_or_healthy(self):
        for values, states, valid in (({}, {}, True), ({"run_feedback": 0}, {"run_feedback": "invalid"}, True),
                                     ({"run_feedback": 0}, {"run_feedback": "stale"}, True),
                                     ({"run_feedback": 2}, {}, True), ({"run_feedback": False}, {}, True),
                                     ({"run_feedback": 1}, {}, False)):
            with self.subTest(values=values, states=states, valid=valid):
                parsed = ParsedPreview(render_preview(design(), profile(), values, states, valid))
                self.assertIn("UNKNOWN", parsed.element_text[1])
                self.assertNotIn("Stopped", parsed.element_text[1])
                self.assertNotIn("Running", parsed.element_text[1])
                self.assertIn("unknown", parsed.element_attrs[1]["class"])

    def test_numeric_limits_large_values_and_unit_are_separate(self):
        doc = design(); doc["tags"][3]["data_type"] = "UDINT"
        doc["screens"][0]["elements"][2]["fractional"] = 0
        parsed = ParsedPreview(render_preview(doc, profile(), {"actual_speed": 4294967295}))
        self.assertIn("4294967295rpm", parsed.element_text[2])
        self.assertIn('<span class="unit">rpm</span>', render_preview(doc, profile()))
        for sample in (-1, 4294967296, 12.3, 12.0, "123"):
            with self.subTest(sample=sample):
                invalid = ParsedPreview(render_preview(doc, profile(), {"actual_speed": sample}))
                self.assertIn("UNKNOWN", invalid.element_text[2])
                self.assertIn("actual_speed", json.loads(invalid.json_data)["invalid_values"])

    def test_input_sample_outside_engineering_limit_is_unknown(self):
        parsed = ParsedPreview(render_preview(design(), profile(), {"speed_setpoint": 5001}))
        self.assertIn("UNKNOWN", parsed.element_text[3])

    def test_split_numeric_input_binding_is_unknown_even_in_conceptual_preview(self):
        doc = design(); doc["tags"][3]["unit"] = "m"
        doc["screens"][0]["elements"][3]["binding"]["read"] = "actual_speed"
        parsed = ParsedPreview(render_preview(doc, profile(), {"actual_speed": 1, "speed_setpoint": 1500}))
        self.assertIn("UNKNOWN", parsed.element_text[3])
        self.assertIn("INPUT BINDING INVALID", parsed.element_text[3])

    def test_omitted_element_unit_still_displays_declared_tag_unit(self):
        doc = design(); del doc["screens"][0]["elements"][2]["unit"]
        self.assertEqual([], validate_design(doc, profile()))
        parsed = ParsedPreview(render_preview(doc, profile(), {"actual_speed": 1420.5}))
        self.assertIn("1420.5rpm", parsed.element_text[2])

    def test_unknown_profile_can_preview_but_exposes_native_gate(self):
        selected = profile(); selected["capabilities"]["button"] = "UNVERIFIED"
        content = render_preview(design(), selected)
        self.assertIn("production blocked", content)
        self.assertIn("Conceptual only", content)
        self.assertIn("no vendor-native source", content)
        self.assertIn("connect-src 'none'", content)
        self.assertNotIn("onclick=", content)

    def test_alarm_active_inactive_and_stale_states_are_distinct(self):
        for value, state, title, klass in ((0, "valid", "ALARMS · 0 ACTIVE", ""),
                                           (1, "valid", "ACTIVE ALARMS · 1", "active"),
                                           (1, "stale", "UNKNOWN", "unknown")):
            with self.subTest(value=value, state=state):
                parsed = ParsedPreview(render_preview(design(), profile(), {"alarm_active": value}, {"alarm_active": state}))
                self.assertIn(title, parsed.element_text[8])
                if klass:
                    self.assertIn(klass, parsed.element_attrs[8]["class"])
                if state == "stale":
                    self.assertIn("STALE", parsed.element_text[8])
                    self.assertNotIn("ACTIVE ALARMS · 1", parsed.element_text[8])

    def test_normal_canvas_has_semantics_without_repeated_sample_labels(self):
        samples = {"run_request": 0, "stop_request": 0, "run_feedback": 1, "actual_speed": 125.5, "speed_setpoint": 150, "alarm_active": 0}
        parsed = ParsedPreview(render_preview(design(), profile(), samples))
        self.assertFalse(any("SAMPLE" in text.upper() for text in parsed.element_text.values()))
        self.assertIn("RUN FEEDBACK", parsed.element_text[1])
        self.assertIn("RUN REQUEST", parsed.element_text[5])
        self.assertIn("Conceptual only", render_preview(design(), profile(), samples))

    def test_nonfinite_preview_data_fails_explicitly(self):
        with self.assertRaises(HmiError):
            render_preview(design(), profile(), {"actual_speed": float("nan")})


if __name__ == "__main__":
    unittest.main()
