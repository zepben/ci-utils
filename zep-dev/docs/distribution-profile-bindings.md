# Distribution · Profile · Bindings

Governing mental model for platform compose/apply in `zep-dev`.

## Problem

The product is a composition of independently developed components. Assembling
that composition only at staging or UAT makes defects expensive and feedback
late. These three concepts make a coherent system a cheap, declarative,
shareable object left of production, without conflating it with a developer
laptop or with production GitOps.

## Three concepts

| Concept | Question | Shareable? |
| --- | --- | --- |
| **Distribution** | What store-backed artefacts constitute this system? | Yes |
| **Profile** | How is that system realized in this environment class? | Yes (no machine-absolute paths) |
| **Bindings** | Where on this machine are the files the Profile assumes? | No |

No Overlay. No live mode. No `branch:` on a Distribution.

```text
Build(Distribution)  →  ensure artefacts in the shared store (OCI)

Apply(Distribution, Profile | Bindings)
  →  realize Profile’s recipe
     installing artefacts named by Distribution
     resolving every required path slot via Bindings

Destroy(Profile metadata [+ saved TF state])
  →  tear down without requiring Distribution or Bindings
```

### Hard rule

If another developer needs the same string for the file to mean the same
thing, it belongs in Distribution or Profile.

If the string is an absolute (or home-only) path on one machine, it belongs
in Bindings.

---

## Distribution

A Distribution is a **bill of materials**: a declarative set of component
identities whose referents are artefacts in a **shared store** (OCI charts).
It is a claim of provenance. Two people with the same Distribution and store
access mean the same system.

### Contains

- Metadata name
- Map of platform components → exactly one store-backed locator each
- Allowed locators:
  - `version:`: immutable published chart pin
  - `pullRequest:` / `commit:`: resolve to a chart version in OCI (build may
    publish into OCI via CI; never via a local chart cache)

### Does not contain

- Kind / cluster topology, Helm values, secrets, passwords
- Host paths, repo paths, mount sources
- `branch:`, dirty trees, local chart caches
- Live / IDE substitution
- Environment class (Kind vs UAT)
- Container image digests as a separate BOM (acknowledged gap; out of scope here)

### Build

`zep-dev distribution build --distribution <path>`

- Idempotent **ensure** each pin exists in the artefact store
- `version:` missing → fail (do not build)
- `pullRequest:` / `commit:` → OCI probe; if missing, dispatch CI and poll.
  Dispatch runs the workflow file from the repo default branch (`ref`) and
  builds the resolved commit SHA (`inputs.commit`) — not the default-branch HEAD.
- Does not start a cluster
- Does not rewrite the Distribution file
- Does not read Bindings or Profile

### Invariants

1. Every locator class ends in shared-store bytes, or fails.
2. Omitting a component means it is not part of this system.
3. A Distribution alone is not runnable; Apply needs a Profile (and Bindings
   when the Profile declares path slots).

---

## Profile

A Profile is a **portable recipe** for realizing a Distribution in a defined
environment class (v1: Kind). It answers how components, data plane, and
contracts are wired, not which chart versions to use.

### Contains

- Metadata name (Kind cluster name in v1; DNS-1123; not `test-cluster`)
- Reference to a Distribution (path in YAML; nested object after load)
- Namespace, inline Kind cluster config, ordered cluster helpers
  (operators, CNPG, access manifests co-located with the Profile)
- App Helm **values** only (not chart identity)
- Secret declarations (env var names; values from the process environment)
- Terraform contract ids when runtime contracts are required
- **Named mount slots**: `slot` + in-cluster `node_path` (host source path
  comes from Bindings)

### Does not contain

- Absolute host paths or machine-specific `~/...` as the source of truth
- Concrete `deployments_root` (that path lives in Bindings)
- `apps.*.chart` filesystem paths
- Component version / PR / commit coordinates (those stay on Distribution)

### Portable exception

Paths **relative to the Profile file** for manifests that travel with the
Profile (for example `access/eas-nodeport.yaml`) are part of the shareable
recipe package. They are not Bindings.

### Apply / destroy

`zep-dev platform apply --profile <path>`

- Load Profile + Distribution; load Bindings; resolve slots
- Preflight: store artefacts, required slots, secrets env, GHCR as needed
- Create/mutate Kind; install helpers; terraform contracts; Helm from OCI
- Does not call `distribution build`
- Does not rewrite YAML

`zep-dev platform destroy --profile <path>`

- Metadata-only load of the Profile name
- Destroy saved terraform roots if present, then delete the Kind cluster
- Must work if the Distribution path is missing or temporarily invalid

### Invariants

1. `apps` keys ⊆ Distribution components.
2. Chart identity comes only from Distribution + artefact store.
3. Required path slots without Bindings → fail before Kind mutate.
4. Existing Kind cluster with the Profile name → fail (no silent reuse),
   unless an explicit operational reuse flag is passed.

---

## Bindings

Bindings are the **private attachment** of a machine to a Profile’s path
requirements. They do not change what the system is.

### Contains (v1)

- Absolute paths only
- `deployments_root`: required when the Profile enables terraform contracts
- `mounts:<slot>` → host directory for each Profile mount slot

Discovery (first file found):

1. `ZEP_DEV_BINDINGS` (path to YAML)
2. `./.zep-dev/bindings.yaml` relative to cwd
3. `${XDG_CONFIG_HOME:-~/.config}/zep-dev/bindings.yaml`

### Does not contain

- Component versions or locators
- Kind topology, Helm values, CNPG specs
- Live sets, branch names, chart-cache policies
- Behaviour flags (package chart, load image): deferred with live

### When used

- Read at Apply (and apply preflight that needs host paths)
- Not read by Build
- Not required by metadata-only Destroy

### Example (local only; do not commit personal paths with examples)

```yaml
deployments_root: /home/you/git/deployments
mounts:
  ewb-data: /home/you/worktmp/archive/max/ewb-data
```

---

## Sharing

```text
Share:  Distribution + Profile
Local:  Bindings (once per machine / checkout layout)
```

Same Distribution + Profile + store access ⇒ same system identity.
Bindings differ per machine without changing that identity.

---

## Ownership

| Layer | Owner |
| --- | --- |
| Distribution / Profile / Bindings tooling | Platform / CI (framework as a service) |
| Integration tests against an applied env | App teams (native test frameworks) |

`zep-dev` provides assemble and Kind apply/destroy. It does not own
application-language integration tests.

---

## Relationship to single-chart CI

`zep-dev cluster create`, `chart lint`, and `chart test` remain the
single-chart Kind CI path on the reserved cluster name `test-cluster`.
They are not the Distribution · Profile · Bindings model. Platform Profiles
must not use `test-cluster` as `metadata.name`.

---

## Non-goals

| Non-goal | Why |
| --- | --- |
| `branch:` on Distribution | Weak provenance; deferred with live |
| Live / IDE artefact substitution | Expands Bindings into policy; deferred |
| Apply calling Build | Couples verbs; hides missing pins |
| Absolute paths on committed Profiles | Breaks shareability |
| Distribution as a “dev session” document | Overloads provenance |
| Non-Kind / UAT Profiles in this model version | Separate environment class later |
| Image digests in Distribution | Separate provenance design |
| Smoke / synthetic tests in customer envs | Different concern |

---

## Doctrine in one sentence

**Distribution is what is true of the system’s artefacts; Profile is how we
run that system in a class of environment; Bindings are how this machine
satisfies the Profile’s path assumptions. Nothing more.**
