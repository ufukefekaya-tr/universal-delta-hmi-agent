# SPDX-License-Identifier: Apache-2.0
"""Stock-frame ancestry and bounded page insertion, with exact inverse evidence."""
from copy import deepcopy
from .hmi4_bootstrap import *
from . import template_catalog as catalog

FIELDS = ('ID', 'wTextLen', 'wTitleTextLen000', 'BgColor')


def audit(raw, profile, pins):
    seed_raw, seed_profile, info = catalog.require_pins(pins)
    require('neutral_page' in info['operations'],'TEMPLATE_QUALIFICATION','Host did not qualify neutral page derivation')
    seed, q = Project(seed_raw), Project(raw); stock = seed.pages[0]
    require(0 < len(q.pages) <= 128, 'NEUTRAL_PAGE_COUNT', 'Neutral frames are limited to 128 pages')
    require(q.file.thumbnail == seed.file.thumbnail and q.file.prefix[:37] == seed.file.prefix[:37]
            and q.file.declared_length == len(q.file.payload), 'NEUTRAL_CONTAINER', 'Container ancestry differs')
    require(q.file.payload[q.index.tail_start:] == seed.file.payload[seed.index.tail_start:],
            'NEUTRAL_RESOURCES', 'Resource/auth/service tail differs from reviewed seed')
    for key in ('schema_version', 'family', 'application_versions', 'model_name', 'panel', 'link', 'station'):
        require(profile.get(key) == seed_profile.get(key), 'NEUTRAL_PROFILE', 'Target contract differs from seed')
    require(q.index.number(q.app, 'DefaultScreen') in {p.page_id for p in q.pages}, 'NEUTRAL_DEFAULT', 'Default screen missing')
    change = token_patch(q, q.app, 'DefaultScreen', seed.index.number(seed.app, 'DefaultScreen'), 'inverse default')
    require(apply_spans(q.file.payload[:q.pages[0].section.start], [change])[0] == seed.file.payload[:stock.section.start],
            'NEUTRAL_PREAMBLE', 'Preamble/auth/global macro ancestry differs')
    names = []
    for page in q.pages:
        require(1 <= page.page_id <= 65534 and not page.elements and len(page.aux) == len(stock.aux),
                'NEUTRAL_PAGE_CONTENT', 'Bounded zero-widget stock frames required')
        edits = [token_patch(q, page.section, k, seed.index.text(stock.section, k) if k.startswith('w')
                             else seed.index.number(stock.section, k), 'inverse neutral field') for k in FIELDS]
        require(block(q, page.section.start, page.end, edits) == seed.file.payload[stock.section.start:stock.end],
                'NEUTRAL_PAGE_SCHEMA', 'Unowned byte in page frame differs')
        name, title = (q.index.text(page.section, k) for k in ('wTextLen', 'wTitleTextLen000'))
        require(name and all(ord(c) >= 32 for c in name+title) and len(name.encode('utf-16-le')) <= 128
                and len(title.encode('utf-16-le')) <= 128, 'NEUTRAL_PAGE_NAME', 'Invalid existing page name/title')
        require(0 <= q.index.number(page.section, 'BgColor') <= 0xffffff, 'NEUTRAL_PAGE_COLOR', 'Invalid page color')
        names.append(name.casefold())
    require(len(set(names)) == len(names), 'NEUTRAL_PAGE_NAME', 'Page names collide')
    profile_check(q, profile)
    return q, seed, stock, info


def build(raw, profile, spec):
    require(set(spec) == {'version', 'operations'} and spec['version'] == 1 and len(spec['operations']) == 1,
            'NEUTRAL_SPEC', 'One neutral insertion per atomic plan')
    op = spec['operations'][0]
    require(set(op) == {'op', 'template_pins', 'new_page_id', 'name', 'background_color'}, 'NEUTRAL_SPEC', 'Exact neutral insertion fields required')
    q, seed, stock, info = audit(raw, profile, op['template_pins'])
    page_id, name, color = op['new_page_id'], op['name'], op['background_color']
    require(len(q.pages) < 128 and type(page_id) is int and 1 <= page_id <= 65534 and all(p.page_id != page_id for p in q.pages),
            'NEUTRAL_PAGE_ID', 'New bounded unique page ID required')
    require(isinstance(name, str) and name and all(ord(c) >= 32 for c in name), 'NEUTRAL_PAGE_NAME', 'Nonempty name without controls required')
    try: encoded = name.encode('utf-16-le', 'strict')
    except UnicodeEncodeError: require(False, 'NEUTRAL_PAGE_NAME', 'Invalid Unicode')
    require(len(encoded) <= 128 and all(q.index.text(p.section, 'wTextLen').casefold() != name.casefold() for p in q.pages),
            'NEUTRAL_PAGE_NAME', 'Bounded unique name required')
    require(type(color) is int and 0 <= color <= 0xffffff, 'NEUTRAL_PAGE_COLOR', 'Packed native 24-bit integer required')
    edits = [token_patch(seed, stock.section, k, v, 'neutral stock field') for k, v in
             dict(ID=page_id, wTextLen=name, wTitleTextLen000=name, BgColor=color).items()]
    clone = block(seed, stock.section.start, stock.end, edits)
    patches = [Patch(q.index.tail_start, q.index.tail_start, b'', clone, 'qualified neutral stock frame')]
    payload, ledger = apply_spans(q.file.payload, patches)
    require(restore_spans(payload, ledger) == q.file.payload, 'INVERSE', 'Neutral insertion inverse differs')
    candidate = q.file.encode(payload); final = Project(candidate); fp = deepcopy(profile)
    from .hmi4_transaction import map_resources
    fp['indexed_layout_sha256'] = layout_digest(final)
    fp['reviewed_resources'] = map_resources(q, profile, payload, patches)
    if str(stock.page_id) in fp.get('background_sha256', {}):
        fp['background_sha256'][str(page_id)] = fp['background_sha256'][str(stock.page_id)]
    fp['neutral_template_pins'] = deepcopy(op['template_pins'])
    audit(candidate, fp, op['template_pins']); validate_references(final)
    return dict(candidate=candidate, profile=fp, ledger=ledger,
                proof=dict(added_page_id=page_id, objects_created=0, exact_inverse=True,
                           stock_page_sha256=sha(seed.file.payload[stock.section.start:stock.end]),seed_sha256=info['seed_sha256'], application_auth_globalmacros_exact=True,
                           resource_bytes_exact=True, native_qualified=False, vendor_compile='NOT_RUN'))


def inspect(service, candidate_sha256, template_id):
    service.checked(candidate_sha256)
    _, _, info = catalog.load(template_id)
    pins = {k: info[k] for k in ('template_id', 'seed_sha256', 'profile_sha256', 'catalog_sha256', 'review_sha256')}
    q, _, _, _ = audit(service.current, service.current_profile, pins)
    return dict(candidate_sha256=candidate_sha256, template_pins=pins, page_limit=128,
                pages=[dict(page_id=p.page_id, name=q.index.text(p.section, 'wTextLen'), title=q.index.text(p.section, 'wTitleTextLen000'),
                            background_color=q.index.number(p.section, 'BgColor'), objects=0) for p in q.pages],
                native_qualified=False, vendor_compile='NOT_RUN')
