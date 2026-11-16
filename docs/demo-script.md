# 2-minute demo script

Goal: show a green PR, a red-team PR turning red, and the fix turning it green. Record the terminal and the GitHub PR page.
Everything below uses commands that exist today; check each against the real repo before filming.

| Time | Screen | Say |
|---|---|---|
| 0:00 | README title + the failing-output snippet | "Prompt evals score text. Cassette checks what the agent did: which tools, which arguments, did it leak a secret." |
| 0:15 | `cd examples/changelogcat && cassette test --offline` -> 9 passed | "Nine recorded runs of a real agent replay in seconds, no API keys, same result every time." |
| 0:35 | `docs/attacks.md` table, then one fixture JSON | "Five prompt-injection fixtures plant hostile PR text. The cassette records the real model's reaction." |
| 0:55 | The red-team PR (label `red-team`), first commit diff: one prompt line | "One line change: tell the model PR text is trusted." |
| 1:10 | PR checks: `live-attacks` failing, job summary showing the added tool calls | "Live replay: the agent starts reading files the baseline never touched. Check is red." |
| 1:30 | Second commit (the revert), checks green | "Restore the line, green again. Fail, fix, pass is in the history." |
| 1:45 | Report `index.html`, then the PR comment | "A static report and one PR comment, kept up to date." |
| 1:55 | Install snippet: `pip install cassette-cli`, Action snippet | "Three commands to start. Link in the description." |

Be honest on screen: offline replay can't see prompt edits (that is why the red-team job is live), and live replay is
not perfectly deterministic.
