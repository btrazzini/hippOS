# Security policy

hippOS handles people's personal memory, so a security problem here can expose private data.

## Reporting a vulnerability

Report it privately: open the repository's **Security** tab and click **Report a vulnerability**. Please don't open a public issue. Say what you found, how to reproduce it and what could be exposed. The maintainer will acknowledge the report and keep you posted on the fix.

## Scope

- The tools in `tools/` and the rules in `system/` and `skills/`.
- Anything that could make an agent write memory outside the `hippOS` folder, leak it into a repository or send it over the network.

Your own memory never belongs in an issue or a pull request: to show a problem, build a throwaway memory from `templates/`.
