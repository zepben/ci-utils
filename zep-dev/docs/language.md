# Ubiquitous language: Development Environments

These terms apply inside the Development Environments context
(`src/zep_dev/development_environments/`; see [context.md](context.md)). Use them
in identifiers, test names, error messages and documentation.

Capital letters matter. **Environment** is the domain term. "Process environment"
means the environment variables given to a child process.

## Terms

| Term | Meaning | Code |
| --- | --- | --- |
| **Environment** | A named local instance: a Kind cluster and the files the tool keeps for it. Identified only by its name. There is no stored record, so state is observed from the cluster and files. It can be partly created. | Policy in `lifecycle.py`. Name rules in `names.EnvironmentName`. |
| **Environment Template** (Template) | A reusable document that describes an Environment: its cluster, supporting services, application configuration and required inputs. Its `metadata.name` names the Environment. | `templates.EnvironmentTemplate` |
| **Distribution** | A named selection of application charts, with one Locator per chart. It can be built without creating an Environment. | `distributions.Distribution` |
| **Locator** | How a Distribution selects one chart: a published version, a pull request, a branch, a commit, or `local: true`. Exactly one field per Locator. | `distributions.ChartLocator` (`VersionLocator`, `PullRequestLocator`, `BranchLocator`, `CommitLocator`, `LocalLocator`) |
| **Chart reference** | A Locator after resolution: a concrete chart name and version, plus the commit for source Locators. Resolution does not check that the chart exists. | `chart_sources.ChartRef` (`VersionChartRef`, `SourceChartRef`, `local_charts.LocalChartRef`) |
| **Application** | One of the Zepben charts a Distribution can select: `ewb`, `eas`, `hcs`, `eas-web-client`. A Template configures an Application under `applications`. | `distributions.ChartName`, `templates.ApplicationConfig` |
| **Supporting service** | A facility an application or test needs, declared in a Template under `services`: a Helm release, a database service, or raw manifests. It is not a Kubernetes Service. Its key names its role in the Environment (`eas-db`); its `type` names how it is provisioned (`helm`, `cnpg`, `raw`). A chart is an Application or a supporting service by its role in the Environment, not by the team that built it. | `services.SupportingService` (`HelmService`, `RawService`, `DatabaseService`) |
| **Database service** | A supporting service that provides named databases to Applications: a primary `database`, further `databases`, an `owner` and `password`, and an address Applications connect to. An Application's `databases` entries name one. Today: a CNPG database cluster. | `services.DatabaseService` (`CnpgService`), `templates.EnvironmentTemplate.database_service`, `terraform.database_address` |
| **Bindings** | Machine-local references that supply the sources for a Template's inputs. They never hold application secret values. | `bindings.Bindings` |
| **Input** | A named requirement a Template declares and Bindings must supply: a mount, a repository (Git checkout) or a secret. | `templates.TemplateInputs` |
| **Secret source** | A Binding for one secret: an environment variable or a file containing `KEY=value` text. Read only when the secret is created. | `bindings.SecretSource` |
| **Execution target** | The addressing of an Environment, derived from its name: cluster `zep-dev-<name>`, context, namespace, kubeconfig and operational directory. Passed explicitly to every call that acts on an Environment's cluster or files. It is not the Environment itself. | `target.ExecutionTarget` |
| **Operational directory** | The files an Environment owns: its kubeconfig and Terraform roots and state, under `${XDG_STATE_HOME:-~/.local/state}/zep-dev/environments/<name>/`. Destroy removes it. Bound inputs are never removed. | `target.ExecutionTarget.directory` |
| **Preflight** | Everything that is loaded, validated and resolved before the cluster or operational directory changes. | `lifecycle.preflight` |
| **Creation plan** | The result of preflight: Template, resolved inputs, execution target, chart references and provisioning data. Resolved once. Provisioning only consumes it. | `lifecycle.CreationPlan` |
| **Provisioning** | Applying a creation plan to a cluster: namespace and storage classes, supporting services, secrets, runtime resources, application manifests, then application charts. | `lifecycle.create_environment` |
| **Kind wrapper** | The Terraform module zep-dev applies to give an Application its runtime contract in an Environment. It calls the Application's runtime contract with the Environment's namespace and database connections, and fills in test settings that production would supply. An Application keeps it in its own repository at `helm/charts/<app>/kind-runtime-contract`; zep-dev applies it whenever the selected chart's revision has one, taking it from that revision. | `chart_sources.ChartResolver.kind_wrapper`, `terraform.RuntimeApplication.module` |
| **Runtime resources** | The Kubernetes resources an Application's Kind wrapper creates. | `terraform.RuntimeApplication`, `terraform.apply_runtime` |

## External terms

These come from outside this repository. Do not rename them.

| Term | Origin |
| --- | --- |
| **Distribution** | The concept in the deployments wiki ("Distribution Concept to Assist Integration Testing"). |
| **EWB**, **EAS**, **HCS**, **web client** | Zepben applications. Chart names `ewb`, `eas`, `hcs`, `eas-web-client`. Source repositories in `chart_sources.REPOSITORIES`: `energy-workbench-server`, `evolve-app-server`, `hosting-capacity-service`, `evolve-web-app`. |
| **Runtime contract** | Terraform modules that create the Kubernetes objects, mostly Secrets and ConfigMaps, that an Application's chart expects by name. An Application keeps them in its own repository under `helm/charts/<app>/runtime-contract/`. |
| **Kind**, **Helm**, **kubectl**, **Terraform**, **CNPG**, **Argo CD** | Tool vocabulary. Kind cluster options, CNPG `spec` and Helm `values` pass through unmodelled. |
