# Migration from the ttsready CLI

The `ttsready` command-line interface is not part of the new workflow. Install
`ssmdconvert` and use its SSMD-aware commands; `ttsready` remains the source-neutral
preparation/QA API used internally by `ssmdconvert`.

| Old command                   | Replacement                                      |
| ----------------------------- | ------------------------------------------------ |
| `ttsready report SOURCE`      | `ssmdconvert report SOURCE`                      |
| `ttsready context SOURCE ID`  | `ssmdconvert context SOURCE ID`                  |
| `ttsready freeze SOURCE ...`  | `ssmdconvert speech freeze SOURCE ... -o OUTPUT` |
| `ttsready txt SOURCE ...`     | `ssmdconvert txt SOURCE ...`                     |
| `ttsready export SOURCE ...`  | `ssmdconvert txt SOURCE ... -o OUTPUT.txt`       |
| `ttsready convert SOURCE ...` | `ssmdconvert txt SOURCE ...`                     |
| `ttsready chapters EPUB`      | `ssmdconvert book inspect EPUB`                  |
| `ttsready preflight SOURCE`   | `ssmdconvert report SOURCE --fail-on-warning`    |

`ssmdconvert convert` converts an input document to SSMD. Use `ssmdconvert txt`
for prepared plain-text projection, adding `-o OUTPUT` for a file destination.

Options are not guaranteed to be identical between the old and new CLIs. Use
`ssmdconvert COMMAND --help` and `ssmdconvert COMMAND SUBCOMMAND --help` for the
supported flags. Chapter selection uses original 1-based source chapter numbers.

Context lookup reads a cached analysis created by `ssmdconvert report`; if the
referenced chapter has changed, refresh the report and use its current generic
change ID. TXT export is a projection from SSMD, not document conversion or an
SSMD write-back operation.

`ttsready lock` / `verify` do not have automatic replacements: do not port them
unless a concrete workflow still needs persisted lock files. `ttsready speakers`
belongs in a future speaker/cast application, not in `ssmdconvert` core. Lexical
review commands are not included in this migration; a future SSMD review command
may use the `ttsready` library API. No compatibility aliases for removed CLI
commands are provided.
