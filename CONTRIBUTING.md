# Contributing

Read AGENTS.md, SYSTEM_PROMPT.md and INDEX.md before a repository task. Keep family parsers and state isolated. Changes need meaningful negative tests, exact saved-file preservation evidence and independent review for native or authorization changes.

Use neutral original fixtures. Do not submit customer projects, PLC symbols, credentials, proprietary vendor assets or code without a clear redistribution license. State exact source/profile/model evidence; do not broaden model support from one fixture.

Original contributions intentionally submitted for inclusion are governed by Apache-2.0 section5 unless explicitly stated otherwise. Keep third-party license and attribution notices with their components. Do not change component snapshots without recording their source commit, version, hashes and tests.

Run `python tools/ci.py install` and `python tools/ci.py test` in a fresh development environment. A development environment may install both packages for test discovery; production uses separate family runtimes.
