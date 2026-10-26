# SPDX-License-Identifier: Apache-2.0
"""Closed current-version resource framing. No alarm/tag/SRAM interpretation."""
from collections import Counter
from copy import deepcopy
import re
import struct
from .common import canonical,hash_value,require,sha
from universal_diascreen_hmi.native import LIMIT,integer
from universal_diascreen_hmi.resources import validate_reviewed_resources

ORDER=('SubMacro','Global_Auxkey','Alarm','History','NewTextBank','Tag','100_SRAM_DATA',
       'Picture','Background','DIATag','DeviceTable','MQTTFile','END')
SYS_BYTES=36
SYS_SHA='449e3965cee4c316f6e169cdefab9965fa7073c114d3dfdc8b8cc0245fcd2a72'
ALARM=set('Version ReadAlarmVar ReadAlarmLink AckAllAlarmLink AckAllAlarmVar SampleCycle RecordNumber Hold '
    'AlmHoldPlace ScreenSaverTiming AlarmTurnOffScrnSaver ScreenDisplayMode ContinueAddr Optimize AlarmExportCSV '
    'wFont001 wFontRatio001 wMessageSize001 EanbleMovingSign Position Direction MoveCount MoveTime '
    'BackgroundColor Opacity AlarmCount'.split())
HISTORY=set('HistoryCtrlAddrContinue HistorySamplingVar HistoryClearVar HistorySamplingStatusVar '
    'HistoryClearStatusVar HistoryFlagAutoClear HistorySampleCycle HistoryCount Optimize'.split())
DEVICE={'EnableDownload','DisplayLength','DisplayFormat'}


def target(q):
    require(q.index.scalar(q.app,'ModelName')=='268502788'
            and q.index.number(q.app,'PanelResWidth')==800 and q.index.number(q.app,'PanelResHeight')==480
            and q.index.scalar(q.app,'Version')=='6.6.2.48' and q.index.scalar(q.app,'NewVersion')=='6.6.2.48'
            and q.index.scalar(q.app,'ApplicationVersion','6.6.2.48')=='6.6.2.48',
            'RESOURCE_TARGET','Only current native6.6.2.48 DOP-107EV800x480 framing is admitted')
    require(not q.index.unqualified_records and q.index.stop_reason=='resource:SubMacro',
            'RESOURCE_INDEX','Qualified indexed prefix and SubMacro tail required')


class Walk:
    def __init__(self,q):
        target(q);self.q=q;self.body=q.file.payload;self.pos=q.index.tail_start
        self.owner=None;self.ordinal=-1;self.seen={};self.counts=Counter();self.frames=[];self.sram=None
        self.header_start=None

    def line(self):
        start=self.pos;end=self.body.find(b'\r\n',start)
        require(end>=0 and end-start<=32768,'RESOURCE_LINE','Truncated/oversized resource record')
        self.pos=end+2;return start,self.body[start:end]

    def take(self,amount):
        require(type(amount) is int and 0<=amount<=LIMIT and self.pos+amount<=len(self.body),
                'RESOURCE_LENGTH','Counted resource exceeds its bounded owner')
        start=self.pos;self.pos+=amount;return start,self.body[start:self.pos]

    def crlf(self):
        require(self.body[self.pos:self.pos+2]==b'\r\n','RESOURCE_FRAME_END','Counted owner terminator is absent')
        self.pos+=2

    def finish(self):
        if self.owner is None:return
        fields=set(self.seen)
        if self.owner=='SubMacro':
            expected={f'SubMacro{kind}{n:03d}' for n in range(1,513) for kind in ('Protect','PWD')}
            require(fields==expected,'RESOURCE_SUBMACRO','Exact stock protection-record set required')
        elif self.owner=='Alarm':
            required=ALARM|{prefix+str(n) for n in range(1,8) for prefix in ('EnableCol','DisplayOrder')}
            require(required<=fields,'RESOURCE_FIELDS','Required Alarm framing metadata is missing')
        elif self.owner=='History':require(fields==HISTORY,'RESOURCE_FIELDS','History metadata differs from the observed shape')
        elif self.owner=='NewTextBank':require('wFont001' in fields and fields<={'wFont001','wFont002','wFont003'},'RESOURCE_FIELDS','Only the observed empty text bank is supported')
        elif self.owner=='Tag':
            count=integer(self.seen.get('TagLinkCount',b''),1)
            require(fields==({'TagLinkCount'} if count==0 else {'TagLinkCount','LinkSize'})
                    and (count==0 or self.seen['LinkSize']==b'0'),'RESOURCE_TAG_FEATURE','Only the observed empty tag-link variants are supported')
        elif self.owner in ('Picture','Background'):require(fields=={'Size'},'RESOURCE_FIELDS','A counted bank needs exactly one Size')
        elif self.owner=='DIATag':require(fields=={'DIATagResource'} and self.seen['DIATagResource']==b'0',
            'RESOURCE_DIATAG_FEATURE','Enabled DIA_TAG resources require their own qualified decoder')
        elif self.owner=='DeviceTable':require(fields==DEVICE,'RESOURCE_FIELDS','Device table metadata differs')
        else:require(not fields,'RESOURCE_FIELDS','Unqualified records in an empty resource owner')

    def header(self,start,name):
        self.finish();self.ordinal+=1
        require(self.ordinal<len(ORDER) and name==ORDER[self.ordinal],
                'RESOURCE_ORDER','Unknown, duplicate or misplaced resource owner')
        self.owner=name;self.header_start=start;self.seen={};self.counts[name]=0
        if name=='100_SRAM_DATA':
            _,prefix=self.take(4);amount=struct.unpack('<I',prefix)[0]
            data_start,data=self.take(amount);self.crlf()
            self.sram=dict(bytes=amount,sha256=sha(data),count_start=data_start-4)
            _,opaque=self.take(SYS_BYTES)
            require(sha(opaque)==SYS_SHA,'RESOURCE_OPAQUE_VARIANT','Post-SRAM opaque record is not the pinned observed variant')

    def field_kind(self,key,value):
        owner=self.owner
        if owner=='SubMacro':
            m=re.fullmatch(r'SubMacro(Protect|PWD)([0-9]{3})',key)
            require(m and 1<=int(m[2])<=512,'RESOURCE_FIELD','Unknown SubMacro record')
            require((value in (b'0',b'1')) if m[1]=='Protect' else len(value)==8,
                    'RESOURCE_SUBMACRO','Unsupported protection record shape')
            return 'scalar'
        if owner=='Alarm':
            if re.fullmatch(r'w(?:Font|FontRatio|MessageSize)00[123]',key) or key in ALARM or re.fullmatch(r'(?:EnableCol|DisplayOrder)[1-7]',key):
                if re.fullmatch(r'wMessageSize00[123]',key):integer(value,4096) # This observed key is a scalar, not a byte count.
                return 'scalar'
            if re.fullmatch(r'Alarm(?:Category|Group|Enable|Color)[0-9]{1,6}',key):return 'scalar'
            if (re.fullmatch(r'w(?:MessageLen|MailContentLen)[0-9]{1,6}-[0-9]{1,6}',key)
                    or re.fullmatch(r'wMail(?:To|CopyTo|BlindCopyTo)Len[0-9]{1,6}',key)):return 'wide'
        elif owner=='History' and key in HISTORY:return 'scalar'
        elif owner=='NewTextBank' and key in ('wFont001','wFont002','wFont003'):return 'scalar'
        elif owner=='Tag' and key in ('TagLinkCount','LinkSize'):
            if key=='LinkSize':require(value==b'0','RESOURCE_TAG_FEATURE','Nonempty tag link data is not qualified')
            return 'scalar'
        elif owner in ('Picture','Background') and key=='Size':return 'bank'
        elif owner=='DIATag' and key=='DIATagResource':return 'scalar'
        elif owner=='DeviceTable' and key in DEVICE:return 'scalar'
        require(False,'RESOURCE_FIELD','Unknown resource record cannot be treated as an ordinary scalar')

    def field(self,start,key,value):
        require(self.owner is not None and key not in self.seen,'RESOURCE_DUPLICATE','Duplicate or unowned resource record')
        kind=self.field_kind(key,value);self.seen[key]=value;self.counts[self.owner]+=1
        if kind=='wide':
            amount=integer(value);_,blob=self.take(amount)
            if amount:
                require(amount>=2 and amount%2==0 and blob[-2:]==b'\0\0','RESOURCE_UTF16','Counted UTF16 shape differs')
                try:blob[:-2].decode('utf-16-le','strict')
                except UnicodeDecodeError:require(False,'RESOURCE_UTF16','Malformed UTF16 resource text')
                self.crlf()
        elif kind=='bank':
            amount=integer(value);blob_start,blob=self.take(amount);self.crlf()
            self.frames.append(dict(section=self.owner,header_start=self.header_start,
                header_sha256=sha(self.body[self.header_start:blob_start]),blob_sha256=sha(blob),
                length_start=start,blob_start=blob_start,blob_end=blob_start+amount,bytes=amount))

    def run(self):
        records=0
        while self.pos<len(self.body):
            records+=1;require(records<=300000,'RESOURCE_RECORD_LIMIT','Too many resource records')
            start,row=self.line()
            head=re.fullmatch(rb'\[([A-Za-z0-9_ -]+)\]',row)
            if head:self.header(start,head[1].decode('ascii'));continue
            if row==b'':continue
            match=re.fullmatch(rb'([A-Za-z][A-Za-z0-9_-]*)=([^\r\n]*)',row)
            require(match is not None,'RESOURCE_RECORD','Unframed resource data cannot be skipped')
            self.field(start,match[1].decode('ascii'),match[2])
        self.finish()
        require(self.ordinal==len(ORDER)-1 and self.owner=='END','RESOURCE_EOF','All observed owners through END are required')
        layout=dict(reviewed_boundary_ack=True,source_payload_sha256=sha(self.body),
            frames=[{k:f[k] for k in ('section','header_start','header_sha256','blob_sha256')} for f in self.frames])
        validate_reviewed_resources(self.q,layout)
        return dict(layout=layout,banks=self.frames,owner_record_counts=dict(self.counts),
            SRAM=dict(bytes=self.sram['bytes'],sha256=self.sram['sha256']),
            opaque_post_SRAM=dict(bytes=SYS_BYTES,sha256=SYS_SHA,meaning_decoded=False),
            ownership='VERSION_PINNED_COUNTED_FRAMING_THROUGH_EOF',semantic_catalogs_decoded=False)


def inspect_banks(service,candidate_sha256):
    service.project_creation.engine();service._loaded();hash_value(candidate_sha256)
    require(candidate_sha256==sha(service.current),'CANDIDATE_HASH','Wrong native resource candidate')
    result=Walk(service._project()).run();profile=deepcopy(service.current_profile)
    profile['reviewed_resources']=result['layout']
    return dict(candidate_sha256=candidate_sha256,**result,resource_profile=profile,
        resource_profile_sha256=sha(canonical(profile)),native_file_written=False,
        native_qualified=False,vendor_compile='NOT_RUN',
        scope='PICTURE_BACKGROUND_BYTE_OWNERSHIP_ONLY; no alarm/tag/SRAM semantics or vendor acceptance')
