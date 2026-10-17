"""Source-pinned maintained BOOL append with new explicit direct addresses.

Stored native intent only. Original resources and executable globals are
retained. New addresses are caller selections, never exclusive allocations.
"""
from copy import deepcopy
import re

from ..errors import HmiError
from . import NativeAdapter, _groups, _screen_extent, _element_extent, _DIA_PREFIX_NAMES
from .codec import MAX_PAYLOAD
from .diascreen_address import DiaScreenAddressNamespace
from .diascreen_control_append import (_COMMON, _BUTTON_HEAD, _BUTTON_TAIL,
    _STATE_KEYS, _scalar, _source_integer, _sha)
from .existing_program import _bounded


MODE = 'diascreen_bound_button_append_v1'
FAMILY = 'delta_diascreen'
VERSION = '6.0.00209.8338'
MODEL = '268502784'
_PIN = re.compile(r'[0-9a-f]{64}')
_ID = re.compile(r'[1-9][0-9]{0,9}')
_PAGE_KEYS = {'screen_id', 'header_sha256', 'aux_sha256', 'owners'}
_CONTRACT_KEYS = {'qualified', 'contract_version', 'mode', 'source_sha256',
    'family', 'model_id', 'serialized_version', 'namespace', 'review_sha256',
    'prefix_sha256', 'tail_sha256', 'pages', 'target_screen_id', 'donor'}
_OP_KEYS = {'op', 'screen_id', 'element_id', 'x', 'y', 'width', 'height',
    'address', 'captions'}
_FONT_NAMES = {b'Arial', bytes.fromhex('b74cb36ea5bfb6c2c5e9')}


def _fail(message, **context):
    raise HmiError('DIA_BOUND_BUTTON', message, **context)


def _pin(value):
    return isinstance(value, str) and _PIN.fullmatch(value) is not None


def _identity(value):
    return isinstance(value, str) and _ID.fullmatch(value) is not None and int(value) <= 0x7fffffff


def _extent(a, owner):
    return b''.join(s.bytes() for s in a.document.sections[owner['start']:owner['end']])


def _color(value):
    n = int(value)
    if not 0 <= n <= 0xffffff:
        _fail('Source COLORREF metadata is outside its stored domain')
    return '#%02x%02x%02x' % (n & 255, (n >> 8) & 255, (n >> 16) & 255)


def bound_button_contract(contract):
    _bounded(contract)
    if (type(contract) is not dict or set(contract) != _CONTRACT_KEYS
            or contract.get('qualified') is not True
            or type(contract.get('contract_version')) is not int or contract['contract_version'] != 1
            or contract.get('mode') != MODE or contract.get('family') != FAMILY
            or contract.get('model_id') != MODEL or contract.get('serialized_version') != VERSION
            or not _identity(contract.get('target_screen_id'))):
        _fail('A separate exact source-bound maintained descriptor is required')
    for key in ('source_sha256', 'review_sha256', 'prefix_sha256', 'tail_sha256'):
        if not _pin(contract[key]):
            _fail('Source and review SHA pins must be canonical', field=key)
    donor = contract['donor']
    if (type(donor) is not dict or set(donor) != {'screen_id', 'element_id', 'owner_sha256'}
            or not all(_identity(donor.get(k)) for k in ('screen_id', 'element_id'))
            or not _pin(donor.get('owner_sha256'))):
        _fail('The complete original maintained donor must be pinned')
    pages = contract['pages']
    if type(pages) is not list or not 1 <= len(pages) <= 256:
        _fail('Source pages require a bounded nonempty pin catalog')
    seen = set()
    for page in pages:
        if (type(page) is not dict or set(page) != _PAGE_KEYS
                or not _identity(page.get('screen_id')) or page['screen_id'] in seen
                or not all(_pin(page.get(k)) for k in ('header_sha256', 'aux_sha256'))
                or type(page.get('owners')) is not list or len(page['owners']) > 4096
                or any(not _identity(v) for v in page['owners'])
                or len(page['owners']) != len(set(page['owners']))):
            _fail('Page identities, extents and ordered owner identities must be exact')
        seen.add(page['screen_id'])
    if contract['target_screen_id'] not in seen:
        _fail('Target page is absent from source pins')
    DiaScreenAddressNamespace._check_contract(contract['namespace'])
    if (contract['namespace']['source_sha256'] != contract['source_sha256']
            or contract['namespace']['model_id'] != MODEL
            or contract['namespace']['serialized_version'] != VERSION):
        _fail('Namespace and control must share the same immutable source')
    return deepcopy(contract)


class DiaScreenBoundButtons:
    """Private source and namespace snapshots; no exposed mutable adapter."""

    def __init__(self, source, contract, authority_raw):
        if not isinstance(source, bytes):
            _fail('A private immutable source byte snapshot is required')
        self._contract = bound_button_contract(contract)
        self._source = NativeAdapter(source, FAMILY)
        self._namespace = DiaScreenAddressNamespace(source, self._contract['namespace'], authority_raw)
        self._check_source()

    def _check_source(self):
        a, c = self._source, self._contract
        NativeAdapter._control_prefix_length(a)
        a._preserved_byte_binding('DIA_BOUND_BUTTON')
        if (_sha(a.original) != c['source_sha256'] or a.model_id != MODEL
                or a.editor_version != VERSION or a.document.bytes() != a.envelope.body):
            _fail('Source bytes or native target identity differs')
        pages = _groups(a.document)
        if len(pages) != len(c['pages']):
            _fail('Original page inventory differs')
        prefix = a.document.sections[:pages[0]['start']]
        if (tuple(s.name for s in prefix) != _DIA_PREFIX_NAMES
                or _sha(b''.join(s.bytes() for s in prefix)) != c['prefix_sha256']
                or _sha(a.document.tail) != c['tail_sha256']):
            _fail('The exact 22-section source prefix and resource tail must be retained')
        self._pages, self._owner_ids, lookup = pages, set(), {}
        for page, pin in zip(pages, c['pages']):
            _screen_extent(a.document, page)
            aux = a.document.sections[page['start'] + 1]
            if (page['id'] != pin['screen_id'] or _sha(page['section'].bytes()) != pin['header_sha256']
                    or aux.bytes() != b'[AuxKeyElement]\r\n' or _sha(aux.bytes()) != pin['aux_sha256']
                    or [o['id'] for o in page['elements']] != pin['owners']):
                _fail('Original page/header/aux/owner order differs')
            if any(_source_integer(page['section'], k, 1, bound) != bound for k, bound in
                    (('DocSizeX', 800), ('PanelSizeX', 800), ('DocSizeY', 480), ('PanelSizeY', 480))):
                _fail('This stored variant requires retained 800x480 source canvases')
            for owner in page['elements']:
                _element_extent(a.document, owner)
                if _scalar(owner['section'], 'GroupID') != '0':
                    _fail('Grouped original owners are outside the append variant')
                self._owner_ids.add(owner['id'])
                lookup[(page['id'], owner['id'])] = owner
        donor = c['donor']
        self._donor = lookup.get((donor['screen_id'], donor['element_id']))
        if self._donor is None or _sha(_extent(a, self._donor)) != donor['owner_sha256']:
            _fail('Original maintained donor extent differs')
        self._check_donor()
        # The actual paired maintained witness proves the new scalar bit slot
        # with the same Type/Sub/storage. It does not qualify toggle execution.
        witnesses = c['namespace']['witnesses']['BOOL']
        if witnesses['read'] != witnesses['write']:
            _fail('Both direct BOOL witnesses must be the same maintained source owner')
        witness = witnesses['read']
        other = lookup.get((witness['screen_id'], witness['element_id']))
        if other is None:
            _fail('The paired direct maintained witness is absent')
        fields = other['section'].fields()
        if any(fields.get(k) != v for k, v in {'Type': '1', 'SubType': '4',
                'MemLen': '0', 'MemFmt': '2', 'WriteReadImmediately': '0'}.items()):
            _fail('The scalar witness must share the same maintained action/storage fields')
        if fields.get('ReadVar') != fields.get('WriteVar'):
            _fail('Direct source witness must read the same command bit it writes')

    def _check_donor(self):
        owner = self._donor
        for index, section in enumerate((owner['section'], *owner['states'])):
            expected = _COMMON + _BUTTON_HEAD + _BUTTON_TAIL if index == 0 else _STATE_KEYS
            if (section.header != ('[' + section.name + ']\r\n').encode()
                    or tuple(r.key for r in section.records) != expected):
                _fail('Donor must retain the exact known ordered resource-free shape')
            for record in section.records:
                if record.kind == 'wide':
                    record.text()
                elif record.kind == 'macro':
                    if record.value != b'0' or record.blob != b'' or record.raw != record.key.encode()+b'=0\r\n':
                        _fail('Donor macro frames must be canonical and empty')
                elif record.kind is not None:
                    _fail('Opaque/picture donor records are unsupported')
                elif index > 0 and record.key == 'FontName0':
                    if record.value not in _FONT_NAMES or record.raw != b'FontName0='+record.value+b'\r\n':
                        _fail('Only the known pinned font-name records may be preserved')
                else:
                    _scalar(section, record.key)
        expected = dict(Type='1', SubType='4', CombineType='0', GroupID='0', Style='2',
            PrintSuccessiveData='0', ReadMemType='0', WriteMemType='0', MemLen='0', MemFmt='2',
            Level='0', OffsetReadMemType='0', OffsetWriteMemType='0', OffsetReadVar='None',
            OffsetWriteVar='None', OffsetMemLen='1', OffsetMemFmt='2', nAngle='0', opacity='255',
            animated='0', antialiasing='1', bFreeze='0', UseBMPText='0', nKeypadTabOrder='0',
            RelatedFileBrowserPartID='-1', PushTime='0', ModifierKey='0', HotKey='0',
            WriteReadImmediately='0', SetLowSecurity='0', VisibleLink='1', VisibleVar='None',
            InterLockLink='1', InterLockVar='None', InterLockLevel='1', InterLockViewMode='0',
            ConFirmWindow='0', NoMessage='0', DispAsterisk='0')
        fields = owner['section'].fields()
        link = self._contract['namespace']['driver']['native_link']
        original_address = self._contract['namespace']['prefix'] + 'D2005.0'
        expected.update(ReadLink=link, WriteLink=link, ReadVar=original_address, WriteVar=original_address)
        if any(fields.get(k) != v for k, v in expected.items()):
            _fail('Donor has unsupported storage, action or dependency settings')
        if fields.get('ReadVar') != fields.get('WriteVar'):
            _fail('Original donor must use one exact command address')
        if len(owner['states']) != 2:
            _fail('Exactly ordered state0 and state1 are required')
        self._fills = []
        for value, state in enumerate(owner['states']):
            state_expected = dict(Value=str(value), FillStyle='0', BorderStyle='0', FontRatio0='100',
                FontAlign='34', FontBold='1', FontItalic='0', FontUnderline='0', UsePictureCoord='0',
                PictureAlign='34', TransEffect='0', TransColor='0', StretchMode='0',
                PictureStretch='0', Twinkles='0', SoundIndex='0')
            if any(_scalar(state, k) != v for k, v in state_expected.items()):
                _fail('Donor state contains an unsupported presentation/dependency flag')
            for k in ('FgColor', 'BgColor', 'FontColor'):
                _source_integer(state, k, 0, 0xffffff)
            _source_integer(state, 'FontSize0', 1, 255)
            self._fills.append(_color(_scalar(state, 'FgColor')))

    def source_metadata(self):
        return {'source_sha256': self._contract['source_sha256'], 'state_fills': self._fills.copy(),
            'native_appearance': 'UNKNOWN', 'scope': 'SOURCE_BOUND_MAINTAINED_STORED_ONLY',
            'fresh_memory': 'NOT_ASSERTED', 'vendor': 'NOT_RUN', 'runtime': 'NOT_RUN'}

    def match_address(self, address):
        self._namespace.match(address, 'BOOL', 'read')
        return self._namespace.match(address, 'BOOL', 'write')

    def _operations(self, operations):
        self._check_source()
        _bounded(operations)
        if type(operations) is not list or len(operations) > 16:
            _fail('At most16 explicitly bound maintained buttons are admitted')
        seen = set()
        for op in operations:
            if (type(op) is not dict or set(op) != _OP_KEYS or op.get('op') != 'append_bound_button'
                    or op.get('screen_id') != self._contract['target_screen_id']
                    or not _identity(op.get('element_id')) or op['element_id'] in self._owner_ids | seen):
                _fail('Bound operation target or fresh identity is invalid/colliding')
            seen.add(op['element_id'])
            for k, maximum in (('x',800), ('y',480), ('width',800), ('height',480)):
                if type(op[k]) is not int or not (1 if k in ('width','height') else 0) <= op[k] <= maximum:
                    _fail('Bound button geometry is outside its typed bounds')
            if op['x']+op['width'] > 800 or op['y']+op['height'] > 480:
                _fail('Bound button extends beyond its source canvas')
            self._namespace.match(op['address'], 'BOOL', 'read')
            self._namespace.match(op['address'], 'BOOL', 'write')
            if type(op['captions']) is not list or len(op['captions']) != 2:
                _fail('Both command states require explicit primary captions')
            for text in op['captions']:
                if not isinstance(text, str) or not text.strip() or '\0' in text or len(text)>512:
                    _fail('Primary state caption is empty or exceeds its bound')
                try:
                    text.encode('utf-16-le', 'strict')
                except UnicodeError as exc:
                    raise HmiError('DIA_BOUND_BUTTON', 'Caption is not valid UTF-16 text') from exc
            if op['captions'][0].strip().casefold() == op['captions'][1].strip().casefold():
                _fail('Maintained command state captions must be distinct')
        return deepcopy(operations)

    def _values(self, op):
        return {'nPartsID':op['element_id'], 'X':str(op['x']), 'Y':str(op['y']),
            'Width':str(op['width']), 'Height':str(op['height']),
            'ReadVar':op['address'], 'WriteVar':op['address']}

    def _expected(self, operations):
        # Whole-BODY oracle uses original raw records, not Record setters.
        insertion = []
        parts = self._source.document.sections[self._donor['start']:self._donor['end']]
        for op in operations:
            values = self._values(op)
            for index, section in enumerate(parts):
                insertion.append(section.header)
                for record in section.records:
                    if index == 0 and record.key in values:
                        insertion.append(record.key.encode()+b'='+values[record.key].encode('ascii')+b'\r\n')
                    elif index > 0 and record.key == 'wTextLen0':
                        blob=op['captions'][index-1].encode('utf-16-le')+b'\0\0'
                        insertion.append(b'wTextLen0='+str(len(blob)).encode()+b'\r\n'+blob+b'\r\n')
                    else:
                        insertion.append(record.raw)
        target = next(p for p in self._pages if p['id']==self._contract['target_screen_id'])
        offset = sum(len(s.bytes()) for s in self._source.document.sections[:target['end']])
        body=self._source.envelope.body[:offset]+b''.join(insertion)+self._source.envelope.body[offset:]
        if len(body)+41 > MAX_PAYLOAD:
            _fail('New native body exceeds the bounded payload')
        return body

    def expected_body(self, operations):
        return self._expected(self._operations(operations))

    def apply(self, operations):
        operations=self._operations(operations)
        if not operations:
            return self._source.original
        document=deepcopy(self._source.document)
        target=next(p for p in _groups(document) if p['id']==self._contract['target_screen_id'])
        insertion=[]
        for op in operations:
            parts=deepcopy(self._source.document.sections[self._donor['start']:self._donor['end']])
            for key,value in self._values(op).items():
                parts[0].one(key).set_value(value.encode('ascii'))
            for text,state in zip(op['captions'],parts[1:]):
                state.one('wTextLen0').set_text(text)
            insertion.extend(parts)
        document.sections[target['end']:target['end']]=insertion
        if document.bytes()!=self._expected(operations):
            _fail('Emitter differs from the original-record splice oracle')
        raw=self._source.envelope.encode(document.bytes())
        self.verify(raw,operations)
        return raw

    def verify(self, candidate, operations):
        operations=self._operations(operations)
        if isinstance(candidate, bytes):
            candidate=NativeAdapter(candidate,FAMILY)
        if not isinstance(candidate,NativeAdapter) or candidate.family!=FAMILY:
            _fail('Saved candidate must be a coherent DIAScreen file')
        candidate._preserved_byte_binding('DIA_BOUND_BUTTON')
        body=self._expected(operations)
        if (candidate.envelope.body!=body or candidate.envelope.thumbnail!=self._source.envelope.thumbnail
                or candidate.envelope.prefix!=self._source.envelope.prefix_for_body(body)
                or candidate.envelope.declared_body_length()!=len(body)
                or candidate.document.tail!=self._source.document.tail):
            _fail('Saved candidate differs from the complete controlled whole-BODY oracle')
        if not operations and candidate.original!=self._source.original:
            _fail('No-op must preserve every original file byte')
        target=next(p for p in _groups(candidate.document) if p['id']==self._contract['target_screen_id'])
        fresh={op['element_id'] for op in operations}
        omitted={i for o in target['elements'] if o['id'] in fresh for i in range(o['start'],o['end'])}
        restored=b''.join(s.bytes() for i,s in enumerate(candidate.document.sections) if i not in omitted)+candidate.document.tail
        if restored!=self._source.envelope.body:
            _fail('Removing only new owners does not restore the original BODY')
        return True
