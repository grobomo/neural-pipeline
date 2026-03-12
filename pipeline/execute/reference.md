# Execute Phase Reference

## Purpose
DO the work. Workers in this phase have full tool access: read, write,
edit, shell, search, list. They carry out the plan steps.

## Manager Role
- Read the Plan phase output for the implementation steps
- Create step files with detailed instructions for each plan step
- Workers in this phase actually create/modify files, run commands, etc.
- Review worker output for correctness AND completeness
- This is the only phase where real changes happen

## Worker Instructions Template
Workers receive specific implementation instructions:
1. What file(s) to create or modify
2. What code to write or commands to run
3. What the expected output should be
4. How to verify the change locally

## Success Criteria Examples
- "File X exists with the required content"
- "Command Y runs without errors"
- "Test Z passes"
- "No syntax errors in modified files"

## Common Pitfalls
- Workers modifying files outside their step's scope
- Skipping verification after making changes
- Not handling error cases in generated code
- Creating files in wrong locations
