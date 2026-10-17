"""Exact common intent, not vendor compiler/keypad qualification."""
from copy import deepcopy
from html.parser import HTMLParser
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.model import new_project
from universal_hmi.preview import render_preview
from universal_hmi.validation import validate_design
from universal_hmi.value_model import (FIXED_MODEL, INTEGER_RANGES,
    raw_to_display, display_to_raw, integer_digits)
from test_design import profile


def fixture(kind="numeric_display", data_type="UINT", fractional=2):
    selected=profile()
    selected["capabilities"]["numeric_value_model:"+FIXED_MODEL]="OFFLINE_PASS"
    document=new_project("raw_integer_decimal_intent",selected["id"])
    document["tags"]=[dict(id="raw",address="DEMO.RAW",data_type=data_type,
        access="ReadWrite" if kind=="numeric_input" else "Read",unit="")]
    element=dict(id="reading",kind=kind,x=20,y=20,width=280,height=100,
        font_size=28,color="#e6edf5",fill="#1b293b",value_model=FIXED_MODEL,
        fractional=fractional,minimum=0,maximum=999,format="decimal",unit="",
        binding=dict(read="raw",write="raw" if kind=="numeric_input" else None))
    document["screens"]=[dict(id="main",name="Main",width=800,height=480,elements=[element])]
    return document,selected


class ValueText(HTMLParser):
    def __init__(self, html):
        super().__init__();self.active=False;self.values=[];self.feed(html)
    def handle_starttag(self, tag, attrs):
        self.active=tag=="span" and "value" in dict(attrs).get("class","").split()
    def handle_data(self, data):
        if self.active:self.values.append(data)
    def handle_endtag(self, tag):
        if tag=="span":self.active=False


class IntegerDecimalIntentTests(unittest.TestCase):
    def test_raw_storage_roundtrip_at_width_extrema_and_fractional_positions(self):
        for data_type,(low,high) in INTEGER_RANGES.items():
            for raw in (low,0,high):
                for fractional in (0,1,4,15):
                    with self.subTest(type=data_type,raw=raw,F=fractional):
                        text=raw_to_display(raw,data_type,fractional)
                        self.assertEqual(display_to_raw(text,data_type,fractional),raw)

    def test_exact_text_padding_sign_and_no_vendor_truncation_in_common_model(self):
        for raw,F,expected in [(0,2,"0.00"),(3,1,"0.3"),(3,2,"0.03"),
                (9,3,"0.009"),(29,2,"0.29"),(123,2,"1.23"),(999,2,"9.99"),
                (-29,2,"-0.29"),(-32768,1,"-3276.8"),(65535,4,"6.5535")]:
            self.assertEqual(raw_to_display(raw,"INT" if raw<0 else "UINT",F),expected)

    def test_display_input_requires_exact_grid_and_storage_bounds(self):
        self.assertEqual(display_to_raw("9.990","UINT",2),999)
        self.assertEqual(display_to_raw("-0.2900","INT",2),-29)
        for text in ("0.291","655.36","-0.01","NaN","Infinity","1e2","+1.2"," 1.2","01.2",""):
            with self.subTest(text=text),self.assertRaises(HmiError):display_to_raw(text,"UINT",2)

    def test_raw_type_width_and_fractional_resources_are_not_converted(self):
        for raw in (True,1.0,0.29,None,"29",65536,-1):
            with self.subTest(raw=raw),self.assertRaises(HmiError):raw_to_display(raw,"UINT",2)
        for data_type in ("BOOL","TIME","REAL","LREAL",None,[],"UINT64"):
            with self.subTest(type=data_type),self.assertRaises(HmiError):raw_to_display(1,data_type,2)
        for F in (-1,16,True,2.0,None):
            with self.subTest(F=F),self.assertRaises(HmiError):raw_to_display(1,"UINT",F)
        with self.assertRaises(HmiError):display_to_raw("1"*97,"UINT",2)

    def test_integer_digits_are_display_domain_and_sign_is_separate(self):
        self.assertEqual(integer_digits(0,999,"UINT",2),1)
        self.assertEqual(integer_digits(0,65535,"UINT",2),3)
        self.assertEqual(integer_digits(-32768,32767,"INT",1),4)
        self.assertEqual(integer_digits(0,65535,"UINT",4),1)
        with self.assertRaises(HmiError):integer_digits(99,1,"UINT",2)

    def test_explicit_model_validates_raw_limits_and_preserves_documents(self):
        document,selected=fixture("numeric_input");original=deepcopy(document)
        self.assertEqual(validate_design(document,selected),[])
        self.assertEqual(document,original)
        document["screens"][0]["elements"][0]["maximum"]=9.99
        self.assertIn("NUMERIC_LIMIT",{x["code"] for x in validate_design(document,selected)})

    def test_model_requires_declared_profile_feature(self):
        document,selected=fixture();selected["capabilities"].pop("numeric_value_model:"+FIXED_MODEL)
        self.assertIn("FEATURE_UNSUPPORTED",{x["code"] for x in validate_design(document,selected)})

    def test_unknown_models_and_noninteger_storage_fail_closed(self):
        for model in (None,[],{},True,"fixed_point","integer_fixed_decimal "):
            document,selected=fixture();document["screens"][0]["elements"][0]["value_model"]=model
            self.assertIn("NUMERIC_VALUE_MODEL",{x["code"] for x in validate_design(document,selected)})
        for data_type in ("REAL","LREAL","TIME"):
            document,selected=fixture(data_type=data_type)
            self.assertIn("NUMERIC_VALUE_MODEL",{x["code"] for x in validate_design(document,selected)})

    def test_without_opt_in_integer_fractional_does_not_acquire_scaling(self):
        document,selected=fixture();element=document["screens"][0]["elements"][0]
        element.pop("value_model")
        self.assertIn("NUMERIC_PRECISION",{x["code"] for x in validate_design(document,selected)})
        element["fractional"]=0
        self.assertEqual(validate_design(document,selected),[])
        before=render_preview(document,selected,values={"raw":123})
        element["value_model"]="raw"
        self.assertEqual(validate_design(document,selected),[])
        self.assertEqual(ValueText(before).values,ValueText(render_preview(document,selected,values={"raw":123})).values)

    def test_initial_html_uses_exact_display_but_checks_raw_range(self):
        document,selected=fixture()
        for raw,text in ((3,"0.03"),(29,"0.29"),(123,"1.23"),(999,"9.99")):
            self.assertIn(text,ValueText(render_preview(document,selected,values={"raw":raw})).values)
        document["screens"][0]["elements"][0]["minimum"]=30
        self.assertIn("UNKNOWN",ValueText(render_preview(document,selected,values={"raw":29})).values)

    def test_shared_tag_has_element_specific_decimal_position(self):
        document,selected=fixture();second=deepcopy(document["screens"][0]["elements"][0])
        second.update(id="another_position",y=160,fractional=1)
        document["screens"][0]["elements"].append(second)
        values=ValueText(render_preview(document,selected,values={"raw":123})).values
        self.assertIn("1.23",values);self.assertIn("12.3",values)

    def test_missing_stale_invalid_and_fractional_raw_samples_are_unknown(self):
        document,selected=fixture()
        for values,states in (({},{}),({"raw":29},{"raw":"stale"}),
                ({"raw":29},{"raw":"invalid"}),({"raw":0.29},{}),({"raw":True},{})):
            self.assertIn("UNKNOWN",ValueText(render_preview(document,selected,values=values,states=states)).values)


if __name__=="__main__":unittest.main()
