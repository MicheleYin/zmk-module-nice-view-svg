# ZMK Module Development Instructions

This repository contains a ZMK module.

## Initialization (first time only)

This repo is created from template. Below template code should be changed when initially starting implementation from template.

- README.md
  - Remove Summary, "Usage" and "More Info" which is for template users. Replace to proper module description.
  - Update "Module User Guide" properly
  - Update CI status badge to link to your repo instead of template repo
- zephyr/module.yml: Change module name properly.
- rename artifact defined in tests/zmk-config/build.yaml properly
- remove this "Initialization" section from AGENT.md (CLAUDE.md is symlink) after confirming all items accomplished.

## Dev Rules

- Commit changes at each milestone. Ensure pre-commit works and never bypass pre-commit check.
- Write simple and sufficient tests for new features.
  - Unit test: Test major functionalities as much as possible by adding case to `tests/<test case>`.
    You might have to add test only logic like executing logic at zephyr initialization to improve test coverage.
  - Build test: Enable feature in `tests/zmk-config/*`. It is to verify build works for real device and to easily test with real device.
    Ensure the feature and device is enabled as expected in the build by verifying output in `test.py`.
- Update README.md properly to guide how to use the module to unfamiliar ZMK keyboard users. Keep the guide simple but sufficient!
- Create pull request to origin after finishing the task

## Workspace Repositories and Integration

This module is integrated into the Sofle firmware through sibling repositories in the user's workspace:

- `zmk-sofle` owns the Sofle shield, keymap, and firmware build configuration.
- `zmk-sofle/config/west.yml` pins the firmware dependency to `https://github.com/MicheleYin/zmk.git` at `feature/nice-view` and this module to `https://github.com/MicheleYin/zmk-module-nice-view-svg` at `feature/nice-view`.
- The ZMK dependency is a custom fork, not upstream `zmkfirmware/zmk`. Check the sibling `zmk` repository when relying on ZMK APIs, configuration, or driver behavior. Do not switch to upstream or assume upstream `main` contains these custom changes.
- The Zephyr module name used by firmware is `zmk-nice-view-plus`.

Use the Sofle manifest for end-to-end firmware integration. From `zmk-sofle`, set up the workspace with `west init -l config`, `west update`, and `west zephyr-export`; use its `build.yaml` as the source of truth for build targets and options.

The standalone test manifests under `west/` currently fetch upstream ZMK `main`. Those tests are useful for module-level checks, but they do not verify compatibility with the custom ZMK fork or replace a Sofle firmware build. For changes that depend on custom ZMK behavior, validate against the Sofle integration workspace.

## Commands

Test command usually takes 1min.

```sh
# Run lint and test when required
pre-commit run
# Run unit test + build test and verify the results
python3 -m unittest
# Run build test directly
west zmk-build tests/zmk-config
# Run unit test directly
west zmk-test tests -m .
```
