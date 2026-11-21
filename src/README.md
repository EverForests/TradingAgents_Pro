# D8 application source

This directory contains the complete application source for the course structure: `tradingagents/`, `cli/` and `main.py`. The inherited runnable packages remain at the repository root to preserve installation, import paths and the original integration history. These copies contain identical source bytes, not separate feature implementations.

[source-manifest.json](source-manifest.json) maps each course source file to its runnable path and hash. Shared source changes must update both views before delivery. The repository keeps upstream regression tests in `tests/` and deterministic course tests in `test/offline/`, with separately authorized checks in `test/live/`. Use the root README commands for the supported suite selection.

Git whitespace checks do not normalize exact source snapshots or raw transcript artifacts. Their source hashes preserve original bytes; runtime lint and the existing CI configuration remain unchanged.
