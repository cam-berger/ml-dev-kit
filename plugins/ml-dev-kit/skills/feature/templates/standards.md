# Standards

How code in this project is built. Build follows these rules, the Reviewer enforces them, and only the human changes them.

## Architecture

- Deep modules: a lot of behaviour behind a small interface, so callers learn little to use one.
- Small interfaces: expose only what callers need. Every public name is something to keep working.
- One responsibility per file, so a reader finds each thing where its name says.
- Reshape only code the Feature touches. Problems elsewhere are reported, not fixed, so each diff stays reviewable.

## Documentation

- Each module starts with a short doc that says why it exists.
- No comments that restate the code. Comment only a why the code cannot show.
- READMEs stay short: what it is, how to run it, where to read more.

## Testing

<!-- The command runs the whole suite and exits 0 when it passes. Test files lists globs, each in its own backticks, comma-separated, such as `tests/**/*.py`, `src/**/*_test.py`. -->
Test command: `<fill in>`
Test files: `<glob>`

- Test through public interfaces at the seams the Spec agrees, so tests survive refactoring.
- Each test name carries its Behaviour ID, such as `test_01_B2_rejects_empty_name`.
- No tautological tests: never assert on a mock, or compute the expected value the way the code does.
- Mock only at system boundaries, such as the network, the clock or a third-party service.

## Baseline

Tests that already failed when this file was written. The test command excludes them.

- none
