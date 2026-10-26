# SPDX-License-Identifier: Apache-2.0
"""Actual saved native text metrics and explicitly synthetic saved-layer previews."""
from pathlib import Path
from io import BytesIO
import base64
from functools import lru_cache
try:
    from PIL import Image,ImageDraw,ImageFont
except ImportError:
    Image=ImageDraw=ImageFont=None
from .hmi4_bootstrap import *
from .hmi4_inspect import family,field,state_row
FONT_FILES={'Arial':('arial.ttf','arialbd.ttf'),'Arial Black':('ariblk.ttf','ariblk.ttf')}
@lru_cache(maxsize=128)
def font(name,size,bold):
    require(name in FONT_FILES,'FONT_UNQUALIFIED','Only pinned Arial/Arial Black local fonts supported')
    require(ImageFont is not None,'DEPENDENCY_UNAVAILABLE','Pinned optional Pillow is required for visuals')
    require(os.environ.get('DIA_HMI_FONT_ROOT'),'FONT_UNQUALIFIED','Trusted host must configure a font root and catalog hashes')
    path=Path(os.environ['DIA_HMI_FONT_ROOT'])/FONT_FILES[name][int(bool(bold))]
    from .hmi4_registry import registry
    raw=no_links(path).read_bytes();pin=sha(raw);require(registry()['font_sha256'][path.name]==pin,'FONT_DRIFT','Pinned font changed')
    f=ImageFont.truetype(BytesIO(raw),size);return f,pin
def color(n):return n&255,n>>8&255,n>>16&255
def fit(q,page_id=None):
    rows=[];fontpins={}
    for p in ([q.page(page_id)] if page_id is not None else q.pages):
        for e in p.elements:
            w=q.index.number(e.section,'Width');h=q.index.number(e.section,'Height')
            for s in e.states:
                st=state_row(q,s)
                for n,text in enumerate(st['text']):
                    if not text:continue
                    f,pin=font(st['font'][n],st['size'][n],st['bold']);fontpins[st['font'][n]+':'+str(st['bold'])]=pin
                    lines=text.split('\n');width=max(f.getlength(t) for t in lines);height=len(lines)*(st['size'][n]+2)
                    rows.append(dict(page_id=p.page_id,element_id=q.index.number(e.section,'nPartsID'),state=st['value'],language=n,width=round(width,3),height=height,available=[w,h],status='PASS' if width<=w and height<=h else 'OVERFLOW'))
    return dict(scope='Actual native text/font fields; host glyph advances, not vendor pixels',checks=len(rows),overflows=[r for r in rows if r['status']!='PASS'],fonts=fontpins,rows=rows,native_qualified=False)
def render(q,profile,page_id,language,values=None):
    require(Image is not None,'DEPENDENCY_UNAVAILABLE','Pinned optional Pillow is required for visuals')
    require(type(language) is int and language in (0,1,2),'LANGUAGE','Indexed native language0/1/2 required');profile_check(q,profile)
    values=values or {};require(isinstance(values,dict) and len(values)<=4096,'FIXTURE','Bounded explicit synthetic values only')
    page=q.page(page_id);frames=validate_reviewed_resources(q,profile['reviewed_resources']);frame=next((f for f in frames if f.section=='Background'),None);require(frame is not None,'BACKGROUND','Reviewed background bank required')
    from universal_diascreen_hmi.preview import decode_dib
    b=decode_dib(q.file.payload[frame.blob_start:frame.blob_end],q.index.number(page.section,'PictureOffset'));im=Image.frombytes('RGB',(800,480),b['rgb']);d=ImageDraw.Draw(im);issues=[]
    for e in page.elements:
        s=e.section;typ=family(q,e);adr=field(q,s,'ReadVar','None');value=values.get(adr,0)
        visible=field(q,s,'VisibleVar','None')
        if visible not in ('','None'):
            if visible not in values:issues.append(dict(code='VISIBILITY_UNEVALUATED',element=q.index.number(s,'nPartsID'),address=visible))
            elif bool(values[visible])!=(not bool(q.index.number(s,'VisibleCondition',0))):continue
        states=[st for st in e.states if q.index.number(st,'Value')==value]
        chosen=states[0] if states else e.states[0];st=state_row(q,chosen);text=st['text'][language]
        if typ[0] in (5,6):
            from .hmi4_inspect import numeric,dec
            n=numeric(q,e);v=(dec(str(value))*dec(n['native_gain'])+dec(n['native_offset']))/dec(n['factor']);text=format(v,'.'+str(n['decimals'])+'f')
        if typ not in ((1,3),(1,4),(1,7),(1,10),(2,1),(5,1),(6,1),(10,6)):
            issues.append(dict(code='FAMILY_UNQUALIFIED',element=q.index.number(s,'nPartsID'),family=typ));continue
        x,y,w,h=[q.index.number(s,k) for k in ('X','Y','Width','Height')]
        if q.index.number(s,'Style',3)==0:d.rectangle((x,y,x+w-1,y+h-1),fill=color(q.index.number(chosen,'BgColor',0)),outline=color(q.index.number(s,'BorderColor',0)))
        if not text:continue
        f,pin=font(st['font'][language],st['size'][language],st['bold']);lines=text.split('\n');lineheight=st['size'][language]+2;top=y+(h-len(lines)*lineheight)/2;align=st['alignment']&7
        for i,line in enumerate(lines):
            tw=f.getlength(line);left=x+2 if align==1 else x+w-tw-2 if align==4 else x+(w-tw)/2
            d.text((left,top+i*lineheight),line,font=f,fill=color(q.index.number(chosen,'FontColor',0)),anchor='lt')
    out=Image.new('RGB',(800,508),'#172D43');out.paste(im,(0,28));draw=ImageDraw.Draw(out);f,_=font('Arial',11,False)
    draw.text((8,8),'SYNTHETIC SAVED NATIVE LAYERS - NOT VENDOR PIXELS OR RUNTIME',font=f,fill='white')
    buffer=BytesIO();out.save(buffer,format='PNG');raw=buffer.getvalue()
    return dict(candidate_sha256=sha(q.file.original),page_id=page_id,language=language,png_base64=base64.b64encode(raw).decode(),png_sha256=sha(raw),issues=issues,scope='SYNTHETIC_NATIVE_SAVED_LAYERS',runtime_qualified=False)
