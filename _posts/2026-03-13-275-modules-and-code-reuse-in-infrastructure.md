---
layout: post
title: "2.7.5 Modules and Code Reuse in Infrastructure"
author: "Glenn Lum"
date:   2026-03-13 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers encounter IaC modules as a packaging mechanism — a way to avoid repeating yourself. The Level 1 framing is accurate: modules encapsulate reusable infrastructure with defined inputs and outputs. But treating modules primarily as a DRY technique misses the actual problem they solve and leads to module designs that create more pain than they prevent. The real function of a module is not to reduce duplication. It is to create a **stable interface contract** that lets infrastructure change in one place and propagate predictably to many. The difference matters because a module designed for reuse looks fundamentally different from a module designed for evolvability — and it's evolvability that you actually need when your pager goes off at 2 AM and a security patch has to roll across every environment you operate.

## How Copy-Paste Actually Compounds

The Level 1 post established that you shouldn't define all infrastructure in one file. But the specific way that copy-paste fails is worth understanding mechanically, because it explains why teams reach for modules and what modules need to solve.

Suppose you define an EKS cluster configuration directly in your root Terraform for the dev environment — node pool sizes, networking rules, IAM roles, encryption settings. Staging needs a cluster too, so you copy the block. Production gets its own copy with different instance sizes. Three copies, all derived from the same source, all understood by the team on day one.

Six months later: dev has an experimental GPU node pool someone added. Prod has a security group rule that was patched during an incident and never backported. Staging has a modified autoscaling policy from a load test that was never reverted. The three copies have **diverged silently**, not because anyone made a bad decision, but because each environment accumulated its own local history.

Now a compliance requirement lands: all clusters must enable envelope encryption for Kubernetes secrets. This is nominally a one-line change. But you cannot apply a uniform patch because the three configurations have different shapes. Each requires its own review, its own plan output, its own risk assessment. The work is not O(1) — "change the pattern once." It's O(n) in the number of copies, with each copy carrying unique cognitive load because you must understand its local mutations before you can safely change it.

This is the compound cost. It's not the initial duplication that hurts. It's the **divergence under maintenance** that makes future changes expensive and error-prone. And the cost grows super-linearly: every additional copy is one more environment that might have drifted in ways the person making the change doesn't know about.

## The Anatomy of a Module Interface

A module in Terraform (or equivalent constructs in Pulumi, OpenTofu, CloudFormation nested stacks) has three structural components that matter: **input variables**, **managed resources**, and **output values**. Together, these form the module's interface contract.

**Input variables** are the knobs you expose to consumers. They define what can vary between uses of the module:

```hcl
variable "cluster_name" {
  type        = string
  description = "Name of the EKS cluster"
}

variable "node_instance_type" {
  type    = string
  default = "m5.large"
}

variable "enable_secret_encryption" {
  type    = bool
  default = true
}
```

**Managed resources** are the infrastructure objects the module creates and controls internally. These are implementation details — the consumer doesn't interact with them directly:

```hcl
resource "aws_eks_cluster" "this" {
  name = var.cluster_name
  # ... internal configuration the consumer doesn't control
  
  encryption_config {
    provider {
      key_arn = var.enable_secret_encryption ? aws_kms_key.eks[0].arn : null
    }
    resources = ["secrets"]
  }
}
```

**Output values** are the information the module exposes for other modules or configurations to consume:

```hcl
output "cluster_endpoint" {
  value = aws_eks_cluster.this.endpoint
}

output "cluster_security_group_id" {
  value = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}
```

The critical design decision — the one that determines whether a module helps or hurts over time — is **where you draw the line between inputs and hardcoded internals**. Every input variable is a degree of freedom you're granting the consumer. Every hardcoded value is an opinion you're enforcing. The compliance requirement from the earlier example? If `enable_secret_encryption` is an input variable defaulting to `true`, any environment could have overridden it to `false`. If encryption is hardcoded as always-on inside the module, compliance is enforced by design with no per-environment opt-out.

This is the module designer's core tension: **flexibility versus consistency**. An overly flexible module with forty input variables has effectively moved all the complexity to the caller — you've built a configuration wrapper around a configuration language, and you haven't actually reduced anyone's cognitive load. An overly rigid module with two inputs is easy to use but gets forked the first time a team needs something slightly different, and now you're back to copy-paste divergence with extra indirection.

## How Modules Compose

Modules rarely exist in isolation. A realistic infrastructure codebase has a root configuration that wires modules together, passing outputs from one as inputs to another:

```hcl
module "network" {
  source       = "git::https://github.com/org/modules.git//network?ref=v2.1.0"
  environment  = "production"
  cidr_block   = "10.0.0.0/16"
}

module "cluster" {
  source            = "git::https://github.com/org/modules.git//eks?ref=v3.0.1"
  cluster_name      = "prod-main"
  vpc_id            = module.network.vpc_id
  subnet_ids        = module.network.private_subnet_ids
}

module "database" {
  source            = "git::https://github.com/org/modules.git//rds?ref=v1.4.0"
  subnet_ids        = module.network.database_subnet_ids
  security_group_id = module.cluster.cluster_security_group_id
}
```

This wiring creates a **dependency graph**. Terraform (and similar tools) builds a directed acyclic graph from these references and uses it to determine the order of operations: network must be created before cluster, cluster before database. The graph is implicit in the references between module outputs and inputs — you don't declare ordering, the tool infers it.

Module composition also means **nested modules** — a module can call other modules internally. Your EKS module might use a smaller IAM-role module and a security-group module under the hood. This creates layers of abstraction. Each layer hides implementation details and exposes a simpler surface.

But nesting has a cost: **debugging depth**. When `terraform plan` shows a change to `module.cluster.module.iam_role.aws_iam_role_policy_attachment.this`, you're three levels deep. Understanding why that change appeared requires traversing the module hierarchy. Deep nesting makes plan output harder to review and increases the time to understand what a change will actually do to your infrastructure.

## Versioning and Upgrade Mechanics

The `?ref=v2.1.0` in the module source is doing critical work. It pins the consumer to a specific snapshot of the module's code. This is what makes module changes safe: updating the module source doesn't affect any consumer until that consumer explicitly bumps their ref.

Module sources can resolve from several places: local file paths (no versioning — always the current code), Git repository tags, a Terraform registry with semantic versions, or artifact storage like S3. The choice determines your upgrade workflow.

With **Git tag pinning**, the upgrade process looks like this: a module maintainer merges changes and cuts a new tag. Each consuming configuration updates its `ref` parameter, runs `terraform plan` to see the impact, reviews the plan, and applies. This is deliberate and explicit — each environment upgrades independently, on its own schedule.

The practical consequence is **version sprawl**. Across fifteen environments, you might have eight different module versions in use. This is not inherently bad — it means each environment upgrades deliberately rather than being forced. But it means that if the module has a security-critical fix in v3.2.0, someone has to track which environments are still on older versions and drive those upgrades. Without tooling or process to manage this, stale versions accumulate silently.

**Breaking changes** in modules — renamed variables, removed outputs, changed resource structures — are particularly painful because they cannot be adopted incrementally. If the module renames `subnet_ids` to `private_subnet_ids`, every consumer must update their calling code at the same time they bump the version. Module maintainers who treat their interfaces as internal implementation details rather than public API contracts cause cascading work across every team that consumes their modules.

## Modules and State Entanglement

Every resource Terraform manages is tracked in the state file under a specific **address** that includes the module path: `module.network.aws_subnet.private[0]`. This address is the binding between the declared configuration and the real infrastructure object.

When you refactor modules — moving a resource from one module to another, renaming a module, splitting a large module into smaller ones — the addresses change. Terraform interprets a changed address as "destroy the old thing, create the new thing." For a subnet with running workloads, that interpretation is catastrophic.

Terraform provides `moved` blocks and the `terraform state mv` command to tell the tool "this resource didn't change, it just moved addresses." But this is manual, error-prone work that requires understanding both the old and new module structures. In a production environment, a state move operation on the wrong resource can cause real outages.

This is the hidden cost of module refactoring. The conceptual change might be clean — "let's split the networking module into separate VPC and subnet modules for better reuse." The state migration is anything but clean. It requires planning, testing against a state copy, coordination with any pipelines that might run concurrently, and often a maintenance window. This cost means module boundaries, once established with real infrastructure behind them, are **expensive to change**. Getting the boundaries roughly right early matters more than in application code, where a refactor is just a refactor.

## Tradeoffs and Failure Modes

### The God Module

The most common failure pattern is a single module that manages an entire environment — networking, compute, databases, DNS, monitoring — all in one. It starts as a convenience: "everything for a service in one module call." But it becomes unmaintainable because any change to any component requires understanding the whole module. It cannot be reused partially. Teams that need "just the networking part" either use the whole thing (pulling in resources they don't want) or fork it (back to copy-paste). The fix is decomposition into single-responsibility modules, but see the state entanglement section above for why that fix is expensive after the fact.

### The Inner Platform

The opposite failure: a module so parameterized that it reproduces the full surface area of the underlying provider. Every resource argument is exposed as a variable, often with `any` types. The module adds no opinions, enforces no standards, and provides no simplification. It's a pass-through layer that adds indirection without adding value. A good module **makes decisions** so its consumers don't have to. If your module's variable count approaches the argument count of the underlying resources, you haven't written a module — you've written a wrapper.

### Premature Abstraction

You extract a module from a single use case, design its interface around that one context, then discover it doesn't generalize to the second use case. But the first team already depends on it in production. Now you're maintaining a module whose interface you want to change but can't, and building a second module that's almost-but-not-quite the same. The standard guidance — wait until you have two or three concrete uses before extracting a module — applies to infrastructure just as it applies to application code, perhaps more so, because the state entanglement makes interface changes costlier.

### Version Drift as Silent Risk

When no one owns the process of tracking module versions across consumers, environments quietly fall behind. The module gets improved, security patches land, but production stays pinned to a version from nine months ago. This isn't visible in any dashboard. It surfaces only when someone tries to make a change and discovers their environment is too far behind to upgrade cleanly, or when an audit reveals that a vulnerability fixed months ago was never rolled out.

## The Mental Model

A module is not a function. It is closer to a **versioned API with state**. Its inputs are the API's parameters. Its outputs are the API's response. Its managed resources are side effects that persist in the real world and are tracked in the state file. Its version tag is the contract that consumers depend on.

This framing changes how you design modules. You think about backward compatibility. You think about what constitutes a breaking change. You think about how many consumers will need to coordinate when the interface evolves. You think about the blast radius of a change — not just "what does this module do?" but "who calls this module, and what are they pinned to?"

The decision of what to put in a module is not "what code is repeated?" It is "what infrastructure should change together, be versioned together, and be constrained together?" That question — what changes together — is the right starting point for every module boundary you draw.

## Key Takeaways

- Copy-paste in infrastructure doesn't fail at creation time — it fails during maintenance, when each copy has silently diverged and a uniform change becomes O(n) work with per-copy risk assessment.

- A module's interface is defined by three components: input variables (what varies), managed resources (what's hidden), and output values (what's shared). The ratio of inputs to hardcoded internals determines whether the module enforces consistency or just relocates complexity.

- Module composition creates an implicit dependency graph. Terraform infers ordering from output-to-input references between modules, and deep nesting increases the cost of reviewing plan output.

- Version pinning makes module upgrades explicit and controlled, but creates a version sprawl management problem that requires active tracking to prevent silent drift across environments.

- Refactoring module boundaries after infrastructure exists requires state migration — not just code changes — making early module boundary decisions disproportionately sticky compared to application code refactoring.

- The "god module" (everything in one) and the "inner platform" (every knob exposed) are opposite failure modes that both result from not deciding what opinions the module should enforce.

- Wait for two or three concrete use cases before extracting a module. Premature abstraction in infrastructure is more costly than in application code because interface changes cascade through state and consumers simultaneously.

- The right question for module boundaries is not "what code is duplicated?" but "what infrastructure should change together, be versioned together, and be constrained together?"

[← Back to Home]({{ "/" | relative_url }})
