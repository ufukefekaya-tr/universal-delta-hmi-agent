# SPDX-License-Identifier: Apache-2.0
"""Host-owned, exact-artifact neutral templates. No seed ships with this package.

Receipts are assertions of the trusted host, not signatures or vendor acceptance.
Job data cannot configure this catalog or qualify its own seed.
"""
from copy import deepcopy
from pathlib import Path
import json
import os
from .hmi4_bootstrap import Project, profile_check
from .common import canonical, sha, require, no_links
from .file_ownership import immutable_read

SCHEMA = 'delta.hmi.template-catalog.v1'
COVERAGE = ('preamble', 'page', 'tail', 'thumbnail', 'prefix')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'CATALOG_DUPLICATE', 'Duplicate JSON member')
        result[key] = value
    return result


def document(raw):
    require(len(raw) <= 2 * 1024 * 1024, 'CATALOG_LIMIT', 'Bounded JSON required')
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda _: require(False, 'CATALOG_JSON', 'Non-finite JSON excluded'))


def path_at(root, name):
    require(isinstance(name, str) and name and len(name) <= 240 and '\\' not in name and ':' not in name
            and all(p not in ('', '.', '..') for p in name.split('/')) and not Path(name).is_absolute(),
            'CATALOG_PATH', 'Normalized catalog-relative path required')
    path = no_links(root / name)
    require(path.resolve().is_relative_to(root.resolve()), 'CATALOG_PATH', 'Catalog path escapes host root')
    return path


def catalog():
    configured = os.environ.get('DIA_HMI_TEMPLATE_ROOT')
    if not configured:
        return None, dict(schema=SCHEMA, templates=[], transitions=[]), None
    root = no_links(configured).resolve(strict=True)
    with immutable_read(path_at(root, 'catalog.json')) as (raw, unchanged):
        value = document(raw); unchanged()
    require(isinstance(value, dict) and set(value) == {'schema', 'templates', 'transitions'} and value['schema'] == SCHEMA,
            'TEMPLATE_CATALOG', 'Unknown host template catalog')
    require(isinstance(value['templates'], list) and len(value['templates']) <= 128
            and isinstance(value['transitions'], list) and len(value['transitions']) <= 512,
            'TEMPLATE_CATALOG', 'Bounded template/transition lists required')
    ids = []
    for entry in value['templates']:
        require(isinstance(entry, dict) and set(entry) == {'id', 'seed', 'profile', 'review', 'target', 'qualification'},
                'TEMPLATE_CATALOG', 'Exact template fields required')
        name = entry['id']
        require(isinstance(name, str) and 1 <= len(name) <= 80 and all(c.isalnum() or c in '_-' for c in name),
                'TEMPLATE_ID', 'Bounded host template identity required')
        ids.append(name)
    require(len(set(ids)) == len(ids), 'TEMPLATE_ID', 'Duplicate template identities')
    seen = set()
    for item in value['transitions']:
        require(isinstance(item, dict) and set(item) == {'from', 'to'} and item['from'] in ids and item['to'] in ids
                and item['from'] != item['to'], 'TEMPLATE_TRANSITION', 'Exact registered blank transition required')
        pair = (item['from'], item['to'])
        require(pair not in seen, 'TEMPLATE_TRANSITION', 'Duplicate transition'); seen.add(pair)
    return root, value, sha(raw)


def read_pin(root, pin):
    require(isinstance(pin, dict) and set(pin) == {'path', 'sha256'}, 'TEMPLATE_PIN', 'Exact host file pin required')
    with immutable_read(path_at(root, pin['path'])) as (raw, unchanged):
        require(sha(raw) == pin['sha256'], 'TEMPLATE_DRIFT', 'Pinned host artifact changed'); unchanged()
    return raw


def coverage(q):
    require(len(q.pages) == 1, 'TEMPLATE_NEUTRAL', 'Exactly one stock page required')
    page = q.pages[0]
    return dict(preamble=sha(q.file.payload[:page.section.start]), page=sha(q.file.payload[page.section.start:page.end]),
                tail=sha(q.file.payload[q.index.tail_start:]), thumbnail=sha(q.file.thumbnail), prefix=sha(q.file.prefix))


def load(template_id):
    root, registry, catalog_sha = catalog()
    rows = [e for e in registry['templates'] if e['id'] == template_id]
    require(root is not None and len(rows) == 1, 'TEMPLATE_UNAVAILABLE', 'No qualified host template with this identity')
    entry = rows[0]; raw = read_pin(root, entry['seed']); profile_raw = read_pin(root, entry['profile'])
    profile = document(profile_raw); receipt = document(read_pin(root, entry['review']))
    from .source_intake import complete_prefix
    q = complete_prefix(Project(raw)); profile_check(q, profile)
    require(len(q.pages) == 1 and not q.pages[0].elements and q.file.declared_length == len(q.file.payload),
            'TEMPLATE_NEUTRAL', 'A counted zero-widget stock frame is required, but is not sufficient qualification')
    # Macro execution is outside this neutral-copy contract even if a host calls it neutral.
    require(all(not t.value or int(t.value) == 0 for section in q.index.sections for t in section.tokens
                if t.key and 'MacroLen' in t.key), 'TEMPLATE_MACRO', 'Neutral templates cannot contain executable macros')
    target = entry['target']
    actual_versions=sorted({q.index.scalar(q.app,k) for k in ('Version','ApplicationVersion','NewVersion') if q.app.one(k,optional=True) is not None})
    require(isinstance(target, dict) and set(target) == {'family', 'model', 'editor_version', 'width', 'height'}
            and target['family'] == 'diascreen-dop100' and isinstance(target['model'], str) and target['model']
            and str(target['model']) == q.index.scalar(q.app, 'ModelName')
            and target['editor_version'] in actual_versions
            and type(target['width']) is int and type(target['height']) is int
            and profile['panel'] == dict(width=target['width'], height=target['height']),
            'TEMPLATE_TARGET', 'Exact native model/editor/resolution profile required')
    qualification = entry['qualification']
    require(isinstance(qualification,dict) and set(qualification)=={'decoder','operations'}
            and qualification['decoder']=='DIASCREEN_PDAB_COUNTED_V1'
            and isinstance(qualification['operations'],list) and 'template_copy' in qualification['operations']
            and len(set(qualification['operations']))==len(qualification['operations'])
            and set(qualification['operations']) <= {'template_copy','neutral_page','target_transition'},
            'TEMPLATE_QUALIFICATION','Unknown decoder or operation scope')
    descriptor_sha=sha(canonical(dict(template_id=template_id,target=target,qualification=qualification)))
    required = {'schema', 'template_id', 'seed_sha256', 'profile_sha256', 'target_sha256', 'descriptor_sha256', 'coverage',
                'origin', 'reuse_rights', 'reviewer', 'auth_review', 'opaque_review', 'status'}
    require(isinstance(receipt, dict) and set(receipt) == required and receipt['schema'] == 'delta.hmi.template-review.v1'
            and receipt['status'] == 'PASS' and receipt['template_id'] == template_id
            and receipt['seed_sha256'] == sha(raw) and receipt['profile_sha256'] == sha(profile_raw)
            and receipt['target_sha256'] == sha(canonical(target)) and receipt['coverage'] == coverage(q),
            'TEMPLATE_REVIEW', 'Exact independent host review must cover every seed owner')
    require(receipt['descriptor_sha256']==descriptor_sha,'TEMPLATE_REVIEW','Decoder/operations/target descriptor review differs')
    require(receipt['origin'] in ('OWNED_NEUTRAL_VENDOR_PROJECT', 'ORIGINAL_SYNTHETIC_OFFLINE_FIXTURE')
            and receipt['reuse_rights'] == 'AUTHORIZED_LOCAL_TEMPLATE_REUSE'
            and isinstance(receipt['reviewer'], str) and receipt['reviewer'].strip()
            and receipt['auth_review'] == 'NO_CUSTOMER_CREDENTIALS_OR_PROJECT_CONTENT'
            and receipt['opaque_review'] == 'EXACT_OWNERS_REVIEWED_NO_CUSTOMER_ASSETS',
            'TEMPLATE_REVIEW', 'Origin, reuse rights, auth and opaque-owner review are mandatory')
    pins = dict(template_id=template_id, seed_sha256=sha(raw), profile_sha256=sha(canonical(profile)),
                catalog_sha256=catalog_sha, review_sha256=entry['review']['sha256'])
    # Re-read registry after artifact reads; replacement during qualification is not accepted.
    require(catalog()[2] == catalog_sha, 'CATALOG_DRIFT', 'Catalog changed during qualification')
    return raw, profile, dict(**pins, target=deepcopy(target), native_header_versions=actual_versions,
                              editor_version_source='SERIALIZED_HEADER_BUILD; running IDE not inspected',
                              operations=deepcopy(qualification['operations']), origin=receipt['origin'],
                              mode='QUALIFIED_TEMPLATE_BYTE_COPY', vendor_qualified=False, vendor_compile='NOT_RUN')


def require_pins(pins):
    raw, profile, info = load(pins['template_id'])
    require(all(pins.get(k) == info[k] for k in ('template_id', 'seed_sha256', 'profile_sha256', 'catalog_sha256', 'review_sha256')),
            'TEMPLATE_DRIFT', 'Plan catalog/seed/profile/review qualification changed')
    return raw, profile, info
