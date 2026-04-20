# Original CI/CD Subproject Prompt

**Date:** 2026-04-20  
**Author:** Esteban Florez

---

## Requirements

We need an environment where features under development can be developed and tested.
Call it dev environment — we need to access it through Tailscale, and CarlosV2 needs to as well.
We will also need a production environment where the latest and greatest version is deployed.

We can have multiple dev environments at a time, each running a different version of the application
with a different set of feature flags activated.

This way we can run a whole battery of tests against each version, and if there is no regression
and the quality is acceptable, it gets tagged in the git repo as a possible release candidate.

## Development Methodology

**I DO NOT want Pull Requests.** We follow:
- **TBD (Trunk Based Development)** — always one main branch
- **TDD** — Test-Driven Development (Red → Green → Refactor)
- **BDD** — Behavior-Driven Development with scenarios

We use **feature flags**, **dark launch**, and **branch by abstraction** to ensure the code is
always on one branch, just behaving differently depending on the environment it is deployed to.

## Architecture

- **Code** lives at Albert's `/home/claude/albert/projects/` (configurable)
- **Dev deployments** happen at CarlosV2 (Hetzner) in Docker containers
- **Prod deployments** happen at CarlosV2 (Hetzner) in Docker containers
- **Access** via Tailscale: CarlosV2 is at `100.122.124.15`

## The ci_cd Agent

Start a subproject inside `~/albert` called `ci_cd`. This will be an agent that, given the
codename of the project and its basic stack (e.g., python), will:
- Create the folder at projects at Albert
- Initialize git
- Create a hello world on its own `.venv`
- Create all README files to start the app
- Add all basic LSP configs, sub-agents, skills, tools, and git hooks
- Add Terraform scripts to generate, deploy, and remove Docker images on demand

## Feature Flag Skills

The basic skills available to the coding agent:

| Skill | Description |
|-------|-------------|
| `start feature <x>` | Creates the feature flag `x` |
| `activate feature <x> in dev` | Deploys software with feature `x` activated in dev |
| `deactivate feature <x> in dev` | Deploys software with feature `x` deactivated in dev |
| `deploy feature <x> in prod` | Deploys software in production with feature `x` DEACTIVATED (dark launch) |
| `release feature <x> in prod` | Activates feature `x` in production |
| `deactivate feature <x> in prod` | Deactivates feature `x` in prod (rollback if regression observed) |

## Tech Stack Support

Initially: **Python**, **HTML**, **JavaScript**

## Validation Test

Use ci_cd to bootstrap:
- **Name:** templateProject
- **Tech Stack:** Django, Python, SQLite (tinysql)
- **Description:** Good to test feature deployment and test.
- **First feature flag:** `testlabel`
