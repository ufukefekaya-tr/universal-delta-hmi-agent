# SPDX-License-Identifier: Apache-2.0
"""Conservative dependency closure shared by legacy and transaction deletion.

Unknown code or resource semantics cannot prove the absence of an incoming edge.
The current proven subset is inert, wholly indexed and has no resource payload.
There is deliberately no caller acknowledgement that bypasses this boundary.
"""
import re
from .errors import require

APP = set('Version ApplicationVersion NewVersion PanelSeries PanelName ModelName PanelResWidth PanelResHeight DefaultScreen InitialMacroLen ClockMacroLen'.split())
ELEMENT = set('nPartsID Type SubType X Y Width Height Style BorderColor ReadVar WriteVar TriggerVar InterLockVar VisibleVar ReadLink WriteLink ReadMemType WriteMemType BeforeExecMacroLen GoToScreenID GoToScreenName rPartID EventID RelatedFileBrowserPartID'.split())
SCREEN = set('ID wTextLen wTitleTextLen000 PictureOffset BgColor DocSizeX DocSizeY PanelSizeX PanelSizeY OpenMacroLen CloseMacroLen CycleMacroLen'.split())
STATE = set('Value FontAlign FontBold FontItalic FontUnderline FontColor FgColor BgColor FillStyle TransEffect Twinkles UsePictureCoord FgFillType BgFillType FgFillStyle BgFillStyle FgFillAngle BgFillAngle'.split())


def closure(q):
    require(not q.index.unqualified_records and q.file.payload[q.index.tail_start:] in (b'', b'[END]\r\n'),
            'DELETE_DEPENDENCY', 'Opaque resource/macro/event dependencies have no qualified deletion closure')
    for page in q.pages:
        require(all(not aux.tokens for aux in page.aux),'DELETE_DEPENDENCY','Auxiliary actions prevent closed inert deletion')
        for e in page.elements:
            require((q.index.number(e.section,'Type'),q.index.number(e.section,'SubType')) in ((2,1),(10,6))
                    and q.index.scalar(e.section,'WriteVar','None') in ('','None')
                    and q.index.scalar(e.section,'TriggerVar','None') in ('','None'),
                    'DELETE_DEPENDENCY','Only wholly known read-only indicator/label families form an inert deletion graph')
    for section in q.index.sections:
        require(section.name in ('Application','Screen','AuxKeyElement','Element','State'),
                'DELETE_DEPENDENCY', 'Unqualified global or event owner prevents deletion')
        for token in section.tokens:
            key=token.key
            require(token.kind!='opaque' and not(token.kind=='macro' and token.blob(q.file.payload)),
                    'DELETE_DEPENDENCY','Executable or opaque dependency prevents deletion')
            allowed=(key in APP if section.name=='Application' else key in SCREEN if section.name in ('Screen','AuxKeyElement')
                     else key in ELEMENT or key=='wDescTextLen0' if section.name=='Element'
                     else key in STATE or re.fullmatch(r'(?:FontName|FontSize|FontRatio|wTextLen)[012]',key or '')
                     or re.fullmatch(r'[FB]gFill(?:Color|EndColor|StopColor[0-4])',key or ''))
            require(allowed,'DELETE_DEPENDENCY','Unknown field semantics prevent a closed dependency graph')
            if key and key.endswith(('PartID','EventID')) and key!='nPartsID':
                require(token.kind=='scalar' and re.fullmatch(rb'-?[0-9]{1,12}',token.value),
                        'DELETE_DEPENDENCY','Unknown object reference expression prevents deletion')
                require(int(token.value) in ((0,-1) if key=='EventID' else (-1,)),
                        'DELETE_DEPENDENCY','Active event or object/group reference prevents a closed deletion graph')
    return 'CLOSED_INERT_INDEXED_EMPTY_RESOURCE_GRAPH'


def check(q,page_id,element_id=None):
    page=q.page(page_id)
    if element_id is None:
        require(q.index.number(q.app,'DefaultScreen',0)!=page_id,'DEFAULT_PAGE','Cannot remove the default page')
        for p in q.pages:
            for e in p.elements:
                if p.page_id!=page_id and q.index.number(e.section,'Type')==1 and q.index.number(e.section,'SubType')==10:
                    require(q.index.number(e.section,'GoToScreenID',-1)!=page_id,'DANGLING_NAVIGATION','Incoming navigation prevents page deletion')
    else:
        e=q.element(page_id,element_id)
        require((q.index.number(e.section,'Type'),q.index.number(e.section,'SubType')) in ((2,1),(10,6))
                and q.index.scalar(e.section,'WriteVar','None') in ('','None')
                and all(not t.blob(q.file.payload) for sec in (e.section,*e.states) for t in sec.tokens if t.kind=='macro'),
                'DELETE_SCOPE','Only macro-free read-only indicators or labels may be removed')
        for section in q.index.sections:
            for token in section.tokens:
                key=token.key or ''
                if key=='EventID':require(token.value in (b'0',b'-1'),'DELETE_DEPENDENCY','Event dependencies prevent deletion')
                if key.endswith('PartID') and key!='nPartsID':
                    require(token.kind=='scalar' and re.fullmatch(rb'-?[0-9]{1,12}',token.value)
                            and int(token.value) in (-1,0),'DELETE_DEPENDENCY','Incoming/grouped/unknown object references prevent deletion')
    return closure(q)
