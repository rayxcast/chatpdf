# Engineering Rules

## Workflow
- Always propose a plan before coding
- Always implement as if opening a production PR
- Avoid broad refactors unless requested
- Keep diffs reviewable

## Testing
- Add or update tests for all behavior changes
- Run relevant tests and linters after changes
- Report exact commands executed
- Explain failing tests before proceeding to fix them optimally

## Code Quality
- Prefer explicitness over cleverness
- Avoid unnecessary abstractions
- Preserve existing architecture patterns or propose optimal changes before implementing them
- Minimize new dependencies, aim for optimal implementation with least dependencies required. Only use dependecies that are truly required for optimal results.

## Observability
- Add structured logging around critical flows
- Include correlation/request IDs where relevant
- Log failures with actionable context
- Avoid noisy logs

## Safety
- Never expose secrets
- Validate all external input
- Consider edge cases and concurrency
- Review for security implications

## Output Format
After implementation provide/update docs/plan.md:
1. Summary of changes
2. Files modified
3. Risks/tradeoffs
4. Tests run
5. Remaining TODOs


# Frontend Design Instructions

When working on frontend UI, prioritize a polished, production-quality visual design over a generic dashboard look.

## Design goals

- Avoid generic “AI app” styling: no bland cards, default gradients, excessive rounded rectangles, or uniform spacing everywhere.
- Create a clear visual identity for this product.
- Use strong hierarchy: clear hero sections, thoughtful typography scale, intentional whitespace, and meaningful contrast.
- Prefer fewer, better-designed components over many generic ones.
- Make screens feel designed, not merely assembled.

## Visual style

- Use a modern editorial/SaaS aesthetic.
- Use restrained color: one primary accent, neutral surfaces, and subtle supporting colors.
- Avoid overusing purple/blue gradients unless specifically requested.
- Use tasteful shadows, borders, background layers, and micro-interactions.
- Add visual rhythm through asymmetry, section breaks, illustration-like empty states, and varied component density.

## UX quality bar

Before implementing, briefly describe the design direction.
When implementing:
- Improve layout, spacing, typography, states, responsiveness, and accessibility.
- Include hover, focus, loading, empty, and error states where relevant.
- Make the mobile layout feel intentionally designed, not merely stacked.
- Do not change product functionality unless asked.

## Components

For every major UI component, consider:
- What is the primary action?
- What secondary information can be visually de-emphasized?
- Is there a more distinctive layout than a plain card grid?
- Does this screen have a memorable visual moment?

## Output expectations

When asked to improve UI:
1. Inspect the existing code and design patterns.
2. Avoid/fix generic UI.
3. Propose a concise design direction.
4. Implement the changes.