#!/bin/bash
# Build the draft: plain text (for reading/diffing) and expanded XML
# (references inlined; ready for datatracker upload once figures/SVGs
# are added).
set -euo pipefail

D=draft-przygienda-fast-flooding-rtx-indication-00

xml2rfc --text "$D.xml"
xml2rfc --allow-local-file-access --expand "$D.xml" -o "$D.expanded.xml"

echo "-- built $D.txt and $D.expanded.xml"
