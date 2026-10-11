# Reviewed SSMD speech-handoff fixture

`reviewed.ssmd` is the stable cross-repository contract fixture. SSMDConvert owns
producing and validating reviewed visible text plus explicit `sub` aliases;
downstream consumers should honor those annotations as the speech authority and
must not recompute them with Spokenform.

The fixture deliberately contains a human-authored acronym alias (`ART`) and a
number alias (`.02`). Tests should preserve both the visible text and the aliases.
The fixture is valid SSMD 0.9 and can be copied into downstream integration tests;
this repository does not modify or require a sibling checkout.
