# Retained upstream notices

`inventory.json` records each redistributed wheel/runtime SHA, source URL and retained notice SHA. Notice files are verbatim upstream material under their respective licenses, not Apache-relicensed project code. Both pinned runtime full-build notice trees are retained; this deliberately includes upstream notices for components that may not be linked in a particular platform. `linked_library_licenses` identifies upstream metadata claims. Two missing full-build notice files (zstd and zlib-ng) were recovered from exact hash-verified upstream source archives; see `runtime-supplemental-sources.json`.

The offline release retains the dependency wheels and Python archives unchanged. License files contained inside those archives remain intact, including pip and setuptools vendored dependencies. This inventory does not assert vendor editor or customer asset rights.

## Runtime source availability

The Linux runtime includes Berkeley DB 6.0.19 in its optional `_dbm` module under the Sleepycat license. Its full source is freely available from https://ftp.osuosl.org/pub/blfs/conglomeration/db/db-6.0.19.tar.gz (SHA256 `2917c28f60903908c2ca4587ded1363b812c4e830a5326aaa77c9879d13ae18e`). The exact runtime build recipes and dependency source URLs/hashes are available at https://github.com/astral-sh/python-build-standalone/tree/20261013 and https://github.com/astral-sh/python-build-standalone/blob/20261013/pythonbuild/downloads.json. CPython source is https://www.python.org/ftp/python/3.14.8/Python-3.14.8.tar.xz. This project source is distributed alongside the binary package. Preserve these source locations and all notices when redistributing. The optional `_dbm` module is not used by the HMI runtime.
