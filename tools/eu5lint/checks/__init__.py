"""Check registries. Add a check module's ``run`` function to one tuple."""

from checks import (
    assets,
    bom,
    braces,
    deadreplace,
    duplicates,
    eol,
    eventids,
    guibraces,
    keywords,
    localization,
    metadata,
    naming,
    overwrite,
    placement,
    prefix,
)
from findings import Finding
from sources import Context, SourceFile
from collections.abc import Iterator, Sequence
from collections.abc import Callable


Check = Callable[[Sequence[SourceFile], Context], Iterator[Finding]]

TIER0: tuple[Check, ...] = (
    bom.run,
    eol.run,
    braces.run,
    overwrite.run,
    keywords.run,
    prefix.run,
    naming.run,
    placement.run,
    localization.run,
    metadata.run,
)
TIER1: tuple[Check, ...] = (
    deadreplace.run,
    eventids.run,
    assets.run,
    duplicates.run,
    guibraces.run,
)
