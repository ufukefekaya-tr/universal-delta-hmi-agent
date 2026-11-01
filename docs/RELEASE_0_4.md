# 0.4.0 distribution contract

The single repository/release contains both isolated families: gateway0.4.0,
DOP-B0.2.1, DIAScreen0.5.0 and the original MITskill0.1.0. MCP code stays Apache-2.0.
Original third-party notices remain unchanged; no vendor installer or customer
project, native seed, symbol catalog, font, logo, credential or runtime database
is a source-package member.

Source collection reads only exact SHA-pinned members of the root implementation
manifest and the two component inventories. The component inventory must itself
be a pinned root member before it is parsed. Source, build/install staging,
wheel data and the six-file skill ZIP have separate membership checks. Tests
include inventory-external sentinels, Windows case aliases, links, changed pins,
duplicate/extra/missing archive members and wrong skill prefixes.

Release assets are source ZIP, Windows offline ZIP, Linux offline TAR.GZ, three
component wheels and the skill ZIP. Offline archives contain only the appropriate
unchanged SHA-pinned B runtime bundle plus current two-family source. DIAScreen
is built from this current source, never the historical0.1.1 archive. Historical
assets retain their original identities.

On Windows the fresh absolute install root is bounded to64 characters before
runtime extraction; no registry or machine policy changes are made. A moved
source package is reinstalled with host-generated paths; installed virtual
environments are not advertised as relocatable. Gateway and test-driver launches
use `-I -B`. Optional Pillow/font support is explicit in the README and is not
promoted to vendor pixel acceptance by structural/text tests.

## Evidence and publication ordering

Repository evidence records local/source acceptance and may say publication is
pending at the source freeze. It cannot contain its own future commit or CI hash.
The external release `RELEASE_AUDIT.json` and `SHA256SUMS.txt` bind the immutable
source commit, exact archives/wheels, independent review, hosted Windows/Linux
results and actual GitHub asset readback. A later metadata-only completion commit
may close the public goal without relabeling the released source or its tests.

Vendor compilation, pixel fidelity and physical panel acceptance remain separate
and are not established by this distribution. The current workflow/goal state is
[the dynamic record](../goals/hmi-skill-transition.json); historical reports remain
historical. See [G5 distribution](../reports/hmi_skill/G5_DISTRIBUTION.json) for the
specific acceptance stage and externally bound publication receipt.
