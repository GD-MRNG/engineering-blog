---
layout: post
title: "2.6.5 Configuration Drift: How Reality Diverges from Declared State"
author: "Glenn Lum"
date:   2026-03-08 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most teams believe they have solved the configuration problem. They use Terraform or Pulumi for infrastructure. They store application config in version control. They inject environment variables through their deployment pipeline. And yet, when an incident occurs at 2am and someone needs to understand what is actually running in production, the answer is: nobody is entirely sure. The configuration files in the repository describe what production *should* look like. What it *actually* looks like is something subtly, dangerously different — and the gap between those two things is where outages hide.

Configuration drift is that gap. The Level 1 understanding — externalize your config, use environment variables, adopt infrastructure-as-code — is necessary but insufficient. Those practices describe how to *declare* desired state. Drift is what happens to actual state after the declaration has been applied. Understanding drift means understanding why declared state and actual state diverge, how that divergence compounds, why it resists detection, and why the most common approaches to preventing it have structural blind spots.

## How Drift Enters a System

Drift does not arrive all at once. It accumulates through a small number of repeating patterns, each of which feels locally reasonable at the time it happens.

**The incident path.** A service is failing in production. The on-call engineer identifies that a connection pool size is too low. The correct fix is to update the configuration in version control, open a pull request, get it reviewed, run it through the deployment pipeline, and wait for it to roll out. The actual fix, at 3am with the pager going off, is `kubectl edit deployment` or an SSH session and a direct edit to a config file. The incident is resolved. The engineer means to backport the change to version control. Sometimes they do. Often they don't — or they do it slightly differently, or they forget one of three changes they made, or they backport it to the wrong branch.

**The imperative escape hatch.** Every declarative system has an imperative bypass. Terraform manages your infrastructure, but the AWS console is always available. Kubernetes manifests describe your workloads, but `kubectl` can mutate any resource directly. Ansible manages server configuration, but SSH still works. These bypasses exist for good reasons — you cannot take away an operator's ability to respond to emergencies. But every imperative change that doesn't flow back through the declarative system creates drift.

**The partial apply.** Configuration management tools can fail partway through a run. Ansible might successfully configure 47 of 48 servers. Terraform might apply 12 of 15 resource changes before hitting an API rate limit. If the failure is noisy, someone investigates. If it's silent — a task that reports "ok" when it should have reported "changed," a resource that is skipped due to a conditional that evaluates differently than expected — the divergence goes unnoticed. You now have a fleet where most nodes match the declared state and a few do not, and nothing in the system is telling you this.

**The forgotten one-off.** A database administrator tunes a PostgreSQL parameter through the console to improve query performance. A security engineer adds a firewall rule directly to address a vulnerability scan finding. A developer adds a cron job to a server to run a one-time data migration and never removes it. Each of these changes is small, documented nowhere except possibly in a Slack thread that will scroll out of searchable history within months. The person who made the change understands it. When that person changes teams or leaves the company, the understanding leaves with them. The change remains.

## Why Declarative Tools Don't Prevent Drift

There is a common misconception that adopting infrastructure-as-code eliminates drift. It does not. It *reduces the rate* of drift and *provides a mechanism* for detecting it, but only if that mechanism is actively and continuously used. The distinction matters.

Most IaC tools operate on a **push model**: a human or a pipeline runs `terraform apply` or `ansible-playbook`, the tool computes the difference between declared and actual state, and it applies changes to close the gap. Between runs, nothing is watching. If someone modifies a resource through the console at 10am and your pipeline runs at 6pm, you have eight hours of undetected drift. If your pipeline only runs on code changes — a common pattern — and no one changes the Terraform files for two weeks, you have two weeks of undetected drift.

Terraform's state file illustrates this precisely. The state file is a **point-in-time snapshot** of what Terraform believes the infrastructure looks like as of the last apply. It is not a live query of actual state. When you run `terraform plan`, Terraform refreshes the state by querying the real infrastructure and compares it against both the current state file and the declared configuration. This is the only moment drift becomes visible. If you never run plan, you never see drift. Many teams run plan only as part of the deployment pipeline, meaning drift is only surfaced when someone is trying to make *new* changes — at which point the plan output includes both the intended changes and a set of unexpected differences that must be understood before proceeding.

Kubernetes has a different model. Its **reconciliation loop** — the core mechanic of its controller architecture — continuously compares actual state against desired state and drives toward convergence. If you manually edit a Deployment's replica count, the Deployment controller will detect the discrepancy and correct it. This is genuinely drift-resistant for the resources that controllers manage. But it has blind spots: ConfigMaps and Secrets are not reconciled against any external source of truth by default. If someone runs `kubectl edit configmap` and changes a value, Kubernetes will faithfully serve the new value to any pod that mounts it. Nothing in the cluster knows that this value no longer matches what is in Git. Tools like ArgoCD and Flux exist specifically to close this gap by adding a reconciliation loop between a Git repository and the cluster state, but they are additions to the platform, not built-in behavior.

The general principle: a declarative tool prevents drift only to the extent that it **continuously reconciles** declared state against actual state and **has authority over all the state** you care about. If reconciliation is periodic or triggered rather than continuous, drift exists in the gaps. If the tool manages only a subset of the configuration surface — Terraform manages the RDS instance but not the parameter group tuning, Ansible manages the package versions but not the runtime configuration files — then drift accumulates in the unmanaged space.

## How Drift Compounds

A single drifted setting is a problem. Drift that has been accumulating for months is a different category of problem, because drift compounds in ways that make it non-linear to resolve.

Consider a concrete scenario. An engineer manually increases the `max_connections` parameter on a PostgreSQL RDS instance from 100 to 200 through the AWS console. This is the initial drift — a single setting that differs from the Terraform configuration. Over the following weeks, the application team notices they can handle more traffic. They deploy more application instances. They adjust their connection pooler's `pool_size` setting to take advantage of the higher connection limit. Another team configures a reporting service that opens its own connections, relying on the headroom. None of these downstream changes reference the manual `max_connections` change; they simply assume the current state of the database.

Now the initial drift has become **load-bearing**. If someone runs `terraform apply` and Terraform resets `max_connections` to 100, the database immediately starts rejecting connections. The application instances fail. The reporting service fails. The root cause — a console edit made weeks ago by someone who may not even remember it — is invisible in the Terraform configuration and the application code. The investigation requires someone to notice the parameter value changed, trace the history in CloudTrail, and understand the cascade of dependencies that were built on top of it.

This is the compounding pattern: initial drift creates a new *de facto* baseline. Subsequent decisions are made against that baseline. Resolving the drift now requires understanding and unwinding all the downstream adaptations, not just reverting a single value.

## The Reproducibility Problem

Drift's most severe consequence is often invisible until you need to reproduce an environment. Disaster recovery, migration to a new region, or spinning up a new environment from scratch all depend on the same assumption: that your declared configuration is complete and correct. If it is, you can rebuild the environment from your repository. If drift has accumulated, the rebuilt environment will match what is in version control — which is not what was running in production.

This is how teams discover that production has been running with an undocumented kernel parameter tuning, or a manually applied database index, or a security group rule that was added during an incident six months ago. The new environment doesn't have these, and things break in ways that are extremely difficult to diagnose because the failure modes don't match any known code change.

The same dynamic applies to staging and development environments. If production has drifted but staging has not (or has drifted differently), the two environments are no longer comparable. Testing in staging provides false confidence because the configuration surface is different in ways nobody can enumerate.

## Tradeoffs in Drift Prevention

The obvious response to drift is strict enforcement: lock down imperative access, require all changes to flow through version control and pipelines, auto-remediate any detected divergence. This works in theory. In practice, it introduces real tensions.

**Enforcement versus emergency response.** If your pipeline takes 20 minutes to deploy a configuration change and your database is running out of connections *now*, the pressure to bypass the pipeline is enormous and arguably correct. Blocking all imperative access means accepting that some incidents will last longer than they need to. Allowing imperative access means accepting drift. The practical middle ground — allow imperative changes during incidents but mandate a post-incident reconciliation step — works only if the reconciliation step is enforced as rigorously as the incident itself. In most organizations, it is not. The incident is over, the pressure is gone, and the backport falls off the priority list.

**Auto-remediation risk.** Continuous reconciliation tools that automatically correct drift sound ideal. But auto-remediation can itself cause incidents. If an operator manually scaled up a service to handle a traffic spike, and the reconciliation loop scales it back down because the Git repository still says 3 replicas, you have now created an outage through your drift-prevention system. ArgoCD addresses this with the concept of **self-heal** being an opt-in behavior per application, and some teams disable auto-sync for critical production resources. But disabling auto-remediation for the resources where drift matters most is a contradiction that reveals the underlying tension: the resources you most want to protect from drift are also the resources where manual intervention is most likely to be necessary.

**Detection without resolution.** A more conservative approach is to detect drift and alert on it without automatically correcting it. This avoids the auto-remediation risk but introduces an alert fatigue problem. If your drift detection system flags dozens of minor discrepancies — a tag that was added manually, a description field that was updated through the console — operators learn to ignore the alerts, and the significant drift gets lost in the noise. Effective drift detection requires the same tuning discipline as any other alerting system: the signal-to-noise ratio must be high enough that alerts drive action.

## The Mental Model

Configuration drift is not a discipline problem. It is an entropy problem. Every system with a mutable state surface and multiple methods of mutation will accumulate undocumented changes over time. The rate of accumulation depends on how many imperative escape hatches exist, how much operational pressure the team is under, and how frequently the system's actual state is compared to its declared state.

The critical insight is that **declared state is an assertion, not a fact**. Your Terraform files, your Kubernetes manifests, your Ansible playbooks — these describe what you *want* to be true. Whether they *are* true at any given moment is a separate question that requires active, continuous verification. The moment you treat your repository as the ground truth of what is running in production, without a mechanism that confirms this, you have created a gap where drift accumulates silently.

The engineering response to drift is not to eliminate the possibility of divergence — that requires eliminating the ability to respond to emergencies, which is unacceptable. It is to minimize the time between divergence occurring and divergence being detected, and to minimize the friction of reconciling actual state back to declared state once it is detected.

## Key Takeaways

- Configuration drift is the divergence between what your version-controlled configuration declares and what is actually running in production; it exists in every system that allows imperative changes alongside declarative management.

- The most common sources of drift are manual changes during incidents, imperative edits through consoles or CLIs that bypass the deployment pipeline, partial failures in configuration management runs, and one-off changes that are never documented.

- Adopting infrastructure-as-code does not prevent drift; it provides a mechanism for *detecting* drift, but only if plan or diff operations are run continuously, not just at deploy time.

- Drift compounds: a single undocumented change becomes load-bearing when subsequent decisions are made against the drifted state, making the drift non-linear to resolve.

- Continuous reconciliation (as in Kubernetes controllers, ArgoCD, or Flux) is structurally more drift-resistant than push-based tools (Terraform, Ansible), but it still has blind spots for resources outside its management scope.

- Auto-remediation of drift can itself cause incidents if it reverts intentional manual changes made during emergency response; the resources most vulnerable to drift are often the same ones where manual intervention is most necessary.

- Drift's most dangerous manifestation is the unreproducible environment: when you cannot rebuild production from your repository because the declared state is incomplete, your disaster recovery capability is compromised in ways you will only discover during an actual disaster.

- Treating your configuration repository as ground truth requires a verification mechanism that continuously confirms the assertion; without that mechanism, the repository is a description of intent, not a description of reality.

[← Back to Home]({{ "/" | relative_url }})
