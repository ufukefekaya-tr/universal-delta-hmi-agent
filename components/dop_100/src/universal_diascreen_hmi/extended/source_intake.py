# SPDX-License-Identifier: Apache-2.0
"""Fresh source profile proposal from complete counted framing, never stale layout."""
import re
from .hmi4_bootstrap import *
from .native_resource_intake import Walk

def complete_prefix(q):
    reason=q.index.stop_reason
    require(not q.index.unqualified_records and (reason=='end' or reason.startswith('resource:')),
            'INDEX_INCOMPLETE','Native index is incomplete at '+str(q.index.tail_start)+': '+reason)
    return q

def intake(raw,source_sha256,expected_link,expected_station):
    hash_value(source_sha256);require(sha(raw)==source_sha256,'SOURCE_HASH','Exact current snapshot hash required')
    q=complete_prefix(Project(raw));require(q.pages,'SOURCE_PAGES','A source with existing pages is required')
    require(isinstance(expected_link,str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,30}',expected_link)
        and q.index.scalar(q.app,'CommName1','')==expected_link,'SOURCE_LINK','Expected link differs from actual native communication name')
    require(type(expected_station) is int and 0<=expected_station<=255
        and q.index.number(q.app,'DefPLCStationNr1')==expected_station,'SOURCE_STATION','Expected station differs from native readback')
    resources=Walk(q).run()  # Closed, counted version/model-specific walk through END.
    profile=dict(schema_version=1,family='diascreen-dop100',panel=dict(width=800,height=480),
        model_name='268502788',application_versions=['6.6.2.48'],link=expected_link,station=expected_station,
        reviewed_index_ack=True,indexed_layout_sha256=layout_digest(q),reviewed_resources=resources['layout'],
        native_source_origin=dict(source_sha256=source_sha256,scope='COMPLETE_INDEX_AND_COUNTED_RESOURCE_FRAMING_ONLY',
            vendor_qualified=False,semantics_imported_from_prior_profile=False))
    profile_check(q,profile);validate_references(q)
    return dict(status='SOURCE_PROFILE_PROPOSAL',source_sha256=source_sha256,engine_sha256=identity(),version=VERSION,profile=profile,
        profile_sha256=sha(canonical(profile)),pages=len(q.pages),objects=sum(len(p.elements) for p in q.pages),
        resource_readback={k:v for k,v in resources.items() if k!='layout'},complete_index=True,
        preserved_only_families=sorted({(q.index.number(e.section,'Type'),q.index.number(e.section,'SubType'))
            for p in q.pages for e in p.elements if q.index.number(e.section,'Type')==3}),
        source_written=False,native_qualified=False,vendor_compile='NOT_RUN',
        next_action='Review actual source/profile hashes; open the immutable workspace snapshot with this fresh profile')
