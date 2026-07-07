# Skills

Domain-specific knowledge Claude Code loads only when relevant to the current task — unlike
`CLAUDE.md`, which loads on every session. Use this for things needed sometimes, not always.

## When to add one here

- Legal objection-detection patterns (once the classifier logic is worked out)
- LiveKit Agents conventions specific to this project
- AMD Developer Cloud / self-hosted vLLM deployment steps

## How to add a skill

Create `.claude/skills/<skill-name>/SKILL.md` with a clear description of *when* Claude should
use it — the description is a trigger, not a summary.

_Empty for now — filled in as real patterns emerge during the build._
