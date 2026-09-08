# Retired cross-source identity inputs

Archived 2026-09-08 after the cross-source identity audit.

`name_aliases.csv` was a name-only FightMatrix list that no loader read. Its
verified claims now live in the source-ID-aware
`data/external/crossorg/identity_overrides.csv`, which is the sole
project-owned identity register. `identity_overrides.csv` contained only a
header and was also unused. They are retained here only as provenance; neither
file is production input.
