#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Stable entry point for humans and automation: run the repository's
# authoritative regression gate. This is a thin wrapper around
# .githooks/pre-commit — it introduces no second set of CI rules; the
# hook remains the single source of truth for what "green" means.
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
exec bash "$repo_root/.githooks/pre-commit"
