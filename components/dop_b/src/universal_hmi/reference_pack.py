"""Explicit private reference transfer. No vendor assets ship in public releases."""
from pathlib import Path
import json
from io import BytesIO
import os
import stat
import uuid
import zipfile

from .errors import HmiError
from .job_policy import canonical, digest, no_links, relative_file
from .job_runner import publish_directory, write_json

MAX_BYTES = 256 * 1024**2
MAX_FILES = 1000


def create_pack(source_root, files, output, *, provenance):
    """Pack an explicit source allowlist; caller records ownership/transfer rights."""
    root = no_links(source_root).resolve(strict=True)
    output = no_links(output)
    if not isinstance(provenance, str) or not provenance.strip():
        raise HmiError('REFERENCE_PROVENANCE', 'Source ownership and transfer-rights reference required')
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise HmiError('REFERENCE_FILES', 'Bounded explicit file list required')
    seen = set(); contents = {}; total = 0
    for name in files:
        path = relative_file(root, name)
        if name.casefold() in seen or name.casefold() == 'reference-manifest.json' or name.split('/')[0].startswith('.'):
            raise HmiError('REFERENCE_FILES', 'Duplicate/reserved/private path')
        seen.add(name.casefold())
        if not path.is_file() or path.stat().st_nlink != 1:
            raise HmiError('REFERENCE_FILES', 'Regular unlinked source files required')
        total += path.stat().st_size
        if total > MAX_BYTES:
            raise HmiError('REFERENCE_SIZE', 'Reference pack exceeds size budget')
        contents[name] = path.read_bytes()
    manifest = dict(schema_version=1, kind='PRIVATE_REFERENCE_PACK', provenance=provenance,
                    files={n:{'sha256':digest(raw),'bytes':len(raw)} for n,raw in contents.items()})
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('reference-manifest.json',canonical(manifest))
        for name, raw in contents.items():archive.writestr(name,raw)
    return {'path':str(output),'sha256':digest(output.read_bytes()),'files':len(contents)}


def import_pack(archive, expected_sha256, destination):
    """Expected archive SHA must arrive through trusted host handoff, not ZIP metadata."""
    archive = no_links(archive); destination = no_links(destination)
    with archive.open('rb') as handle:
        archive_bytes = handle.read(MAX_BYTES+1)
    if len(archive_bytes) > MAX_BYTES or digest(archive_bytes) != expected_sha256:
        raise HmiError('REFERENCE_HASH', 'Archive does not match trusted transfer SHA')
    if destination.exists() or not destination.parent.is_dir():
        raise HmiError('REFERENCE_TARGET', 'New destination under an existing parent required')
    with zipfile.ZipFile(BytesIO(archive_bytes)) as source:
        infos=source.infolist()
        if not 2 <= len(infos) <= MAX_FILES+1 or sum(i.file_size for i in infos)>MAX_BYTES:
            raise HmiError('REFERENCE_SIZE','Invalid reference size/count')
        seen=set()
        for info in infos:
            relative_file(destination.parent,info.filename)
            mode=info.external_attr >> 16
            if (info.filename.casefold() in seen or info.is_dir() or info.flag_bits & 1
                    or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0,stat.S_IFREG))):
                raise HmiError('REFERENCE_FILES','Duplicate, directory, encrypted or special ZIP entry')
            seen.add(info.filename.casefold())
        def unique(pairs):
            result={}
            for key,value in pairs:
                if key in result:raise HmiError('REFERENCE_MANIFEST','Duplicate JSON key')
                result[key]=value
            return result
        try:
            manifest=json.loads(source.read('reference-manifest.json'),object_pairs_hook=unique)
        except (KeyError,ValueError,UnicodeError) as exc:
            raise HmiError('REFERENCE_MANIFEST','Invalid reference manifest') from exc
        if (not isinstance(manifest,dict) or set(manifest)!={'schema_version','kind','provenance','files'}
                or type(manifest['schema_version']) is not int or manifest['schema_version']!=1
                or manifest['kind']!='PRIVATE_REFERENCE_PACK' or not isinstance(manifest['provenance'],str)
                or not manifest['provenance'].strip() or not isinstance(manifest['files'],dict)
                or set(manifest['files']) | {'reference-manifest.json'} != {i.filename for i in infos}):
            raise HmiError('REFERENCE_MANIFEST','Exact reference manifest required')
        # Verify every byte before creating destination files.
        contents={}
        for name,pin in manifest['files'].items():
            if name.split('/')[0].casefold() == 'reference-manifest.json' or name.split('/')[0].startswith('.'):
                raise HmiError('REFERENCE_FILES','Reserved/private reference path')
            raw=source.read(name)
            if pin != {'sha256':digest(raw),'bytes':len(raw)}:
                raise HmiError('REFERENCE_HASH','Reference entry changed',path=name)
            contents[name]=raw
    stage=destination.with_name('.reference-'+uuid.uuid4().hex);stage.mkdir()
    for name,raw in contents.items():
        path=relative_file(stage,name);path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as handle:
            handle.write(raw);handle.flush();os.fsync(handle.fileno())
    write_json(stage/'reference-manifest.json',manifest)
    publish_directory(stage,destination)
    return {'path':str(destination),'sha256':expected_sha256,'files':len(contents),'kind':'PRIVATE_REFERENCE_PACK'}
