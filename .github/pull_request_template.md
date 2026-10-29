## What and why

<!-- The case that failed and what this changes. Link the issue. -->

## Checklist

- [ ] `python3 -m py_compile tools/memory.py tools/lookup.py`
- [ ] `tools/version.sh` passes (word budget), and the version was bumped if a rule changed
- [ ] Protocol, skills and validator changed together, if a rule changed
- [ ] Tested on a throwaway memory built from `templates/`
- [ ] No personal data (names, clients, amounts, decisions, contacts)
