# NexAgent Workspace Rules

## Delivery governance

- Use **Plane** as the sole source of truth for delivery work: initiatives, epics, milestones, issues, priorities, status, bugs, and implementation progress.
- Use **DocMost** as the sole source of truth for product and technical documentation: vision, requirements, architecture, ADRs, API design, learning notes, and release notes.
- Use the connected **Plane** and **DocMost** MCP services for their respective systems. Do not use another task tracker or documentation service for NexAgent unless the user explicitly changes this rule.
- Before implementing a meaningful change, ensure it is represented by a Plane issue with clear acceptance criteria. Update it as work progresses and when it is completed.
- Document material product or architecture decisions in DocMost and link the relevant Plane issue whenever possible. Design pages should state their purpose, status, and related Plane issue(s).
- Record validation performed (tests, build, or manual verification), modified files, and follow-up work in the relevant Plane issue.
- Do not create a parallel task tracker, roadmap, requirements document, or architecture wiki in this repository. This file is an operational rule, not product documentation.
- If Plane or DocMost cannot be accessed, tell the user and ask for direction rather than silently substituting another system.
- Never place API keys, personal-access tokens, bearer tokens, or MCP credentials in the repository, Plane issues, or DocMost pages.

## Engineering practice

- Work in small, independently verifiable Plane issues.
- Keep NexAgent local-first and security-conscious: do not expose secrets, leave the project root without authorization, or execute destructive commands without explicit approval.
