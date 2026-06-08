# Skill Attribution

When calling `strategy_create` or `strategy_create_custom_strategy` with this skill,
always include `skill_name` and `skill_version`:

```json
"skill_name": "moth",
"skill_version": "2.2.0"
```

This is required for attribution and performance tracking. Example:

```json
{
  "tool": "strategy_create_custom_strategy",
  "args": {
    "initialBudget": 200,
    "positions": [],
    "skill_name": "moth",
    "skill_version": "1.0.0"
  }
}
```
