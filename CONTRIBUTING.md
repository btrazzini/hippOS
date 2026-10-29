# Contributing to hippOS

Thanks for your interest. hippOS is open source (MIT): anyone can fork it, change it and use it freely. This repository is curated by its maintainer, who decides what goes in: changes come through pull requests and are merged only after the maintainer's review.

## Before opening a pull request

- For anything beyond a small fix, open an issue first, so we can agree on the change before you write it.
- hippOS is memory for an executive. Every change answers "does this help an executive carry less in their head?" (see `system/inspirations.md`).
- The rules have a word budget, and `tools/version.sh` refuses to go over it. A new rule comes with the case that failed, and for one to come in, another leaves or merges. What is mechanical goes into code, not text (see `AGENTS.md`).
- A rule change touches the protocol, the skills and the validator together, and bumps the version with `tools/version.sh <new>`.
- Never include anyone's personal data: no real names, clients, amounts, decisions or contacts. Examples use generic placeholders.
- Keep it in English and free of dependencies (Python 3.8+ standard library only).

## Checks

```
python3 -m py_compile tools/memory.py tools/lookup.py tools/guard.py
tools/version.sh
```

Then run the tools against a throwaway memory built from `templates/`, never against a real one.

## Security

If you find something that could expose someone's memory, report it privately (see [SECURITY.md](SECURITY.md)) instead of opening a public issue.

## License

By contributing, you agree that your contribution is licensed under the MIT License, like the rest of hippOS.
