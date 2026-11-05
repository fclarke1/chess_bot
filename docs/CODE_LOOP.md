# Code loop

Follow this loop for each step in [PLAN.md](./PLAN.md). Do not skip a stage. Do not start the next step before the loop for the current step is complete.

## 1. Write

1. Create a branch from `main` with the name in the plan.
2. Write the code and its tests. Keep the rules in [ARCHITECTURE.md](./ARCHITECTURE.md), "MicroPython constraints".
3. Run `uv run pytest`. All tests must pass.
4. Run the MicroPython runner with `micropython -X heapsize=100K <runner>`. All checks must pass.
5. Commit.

## 2. Simplify

1. Start an agent with this brief: the files of the step, their tests, and the purpose of the step in one sentence. Ask it to find code that is more abstract, more general, or longer than the purpose needs. Ask for a concrete simpler version of each finding. Give it the code, not your opinion of the code.
2. Read each finding. Apply the ones that make the code shorter or easier to read with no loss of function. Reject the ones that add a dependency, break a MicroPython constraint, or only move complexity.
3. Run both test runs again. Commit.

## 3. Check

1. Start a second agent with this brief: the files, their tests, and the purpose. Ask it to find inputs where the code gives a wrong result, breaks a rule in ARCHITECTURE.md or CONTEXT.md, or fails on MicroPython. Ask for a concrete scenario per finding. Do not give it the simplification findings.
2. Verify each finding with a test before you change code. A finding with no failing test is not a fault.
3. Fix the confirmed faults. Keep the new tests.
4. Run both test runs again. Commit.

## 4. Close

1. Push the branch and merge it to `main` with a fast-forward merge.
2. Update PLAN.md: mark the step done, and write any new fact that changes a later step.
3. Report to the owner: what was built, what the agents found, what was applied and what was rejected and why, and the heap use in MicroPython.

## Rules for the whole loop

- Simple before general. Write a function for the case that exists, not for the cases that may exist.
- One file per concern, as listed in ARCHITECTURE.md. Do not add a layer, a base class, or a registry that the plan does not name.
- A name from CONTEXT.md is the only name for that concept in code, comments, and tests.
- Each agent gets a narrow brief: the files, the purpose, and what you already ruled out. It does not get your conclusions.
- Apply a finding only when you agree with it. Record a rejected finding and the reason in the step report.
