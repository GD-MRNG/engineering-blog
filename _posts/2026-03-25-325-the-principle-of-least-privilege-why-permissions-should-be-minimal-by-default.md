---
layout: post
title: "3.2.5 The Principle of Least Privilege: Why Permissions Should Be Minimal by Default"
author: "Glenn Lum"
date:   2026-03-25 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most engineers understand least privilege as a hygiene rule: don't give things more access than they need. This understanding is correct and almost entirely useless. The gap is not in knowing *what* least privilege means — it's in understanding the mechanics that make it either effective or decorative. Specifically: how do permission systems actually evaluate access? How does privilege escalation work as a concrete chain of operations, not an abstract threat? What does "blast radius" actually look like when you trace it through a real permission graph? And why do well-intentioned teams consistently end up with environments where every service account can reach everything?

The answers to these questions are what separate a team that *states* least privilege as a value from a team that *achieves* it in production.

## How Permission Evaluation Actually Works

Every cloud permission system — AWS IAM, GCP IAM, Azure RBAC, Kubernetes RBAC — operates on the same fundamental model: an **identity** makes a **request** against a **resource**, and a **policy evaluation engine** decides whether to allow or deny it. The mechanics of that evaluation are where least privilege lives or dies.

In AWS IAM, when a request arrives, the engine collects every policy that could apply: identity-based policies (attached to the user or role), resource-based policies (attached to the target resource), permission boundaries (an upper bound on what the identity *can* be granted), session policies (for temporary credentials), and organizational service control policies (SCPs). The final authorization is not a simple union of all these grants. It's a series of intersections and overrides. An explicit deny in *any* policy wins. If there's no explicit deny, the engine looks for an explicit allow. If no policy explicitly allows the action, it's denied by default.

This means the effective permissions of an identity are the **intersection** of all applicable policy layers, not the union. This is genuinely non-obvious and has practical consequences. You can attach an IAM policy granting `s3:*` to a role, but if a permission boundary on that role only allows `s3:GetObject`, the effective permission is `s3:GetObject`. If an SCP on the AWS Organization denies access to a specific region, no identity in any account under that organization can operate in that region, regardless of what their identity policies say.

Understanding this layered evaluation model is what lets you implement least privilege architecturally rather than just hoping individual policies are correct. Permission boundaries and SCPs act as guardrails — they define the maximum possible access, and individual policies can only grant access *within* that envelope. A misconfigured identity policy can't exceed its boundary. This is the difference between a system where one mistake creates a breach and a system where one mistake is contained by the layer above it.

Kubernetes RBAC works differently in one important respect: it is **additive only**. There are no deny rules. A subject (user, group, or service account) can do anything that *any* bound Role or ClusterRole permits. This means in Kubernetes, the only way to restrict access is to not grant it in the first place. You cannot patch over an overly broad RoleBinding with a narrower one — you have to remove or replace the broad binding. This makes permission auditing in Kubernetes clusters qualitatively harder than in systems with explicit deny support.

## The Permission Graph and Why Blast Radius Is Not a Metaphor

"Blast radius" sounds like a metaphor. It is more useful to treat it as a literal graph traversal.

When an attacker compromises a workload, they inherit that workload's effective permissions. Those permissions are edges in a graph connecting the compromised identity to every resource it can access and every action it can perform. Some of those actions lead to *other* identities — and this is where escalation happens.

Consider a concrete scenario. A service account for a data pipeline has the following permissions: `s3:GetObject` and `s3:PutObject` on a specific data bucket, `logs:PutLogEvents` for writing logs, and `iam:PassRole` for passing a specific role to an EMR cluster it launches. If this account is compromised, the attacker can read and write objects in one bucket and write logs. The blast radius is small and well-defined.

Now consider the common alternative: the same service account, but instead of scoped permissions, it was given the managed policy `PowerUserAccess` because the team needed to iterate quickly and kept hitting permission errors. This identity can now create Lambda functions, spin up EC2 instances, read from any S3 bucket in the account, modify DynamoDB tables, and do nearly anything except manage IAM users directly. The blast radius is the entire account.

But the real damage comes from **transitive access**. If that overpermissioned identity can call `iam:PassRole` on a broadly trusted role, or `sts:AssumeRole` on a cross-account role, the attacker doesn't just have access to one account — they can pivot. Each hop in the graph multiplies the reachable surface. Tools like Cartography, PMapper, and CloudSplaining exist specifically to map these transitive permission paths, because they are invisible if you only inspect one policy at a time.

This is the core insight: **least privilege is not about individual policies. It is about minimizing the reachable subgraph from any single compromised node.** A policy that looks reasonable in isolation can be catastrophic if it connects to a high-privilege path.

## How Privilege Escalation Actually Works

Privilege escalation is not a single exploit. It is a chain of individually authorized operations that, in combination, yield higher privileges than any single step was intended to grant.

In AWS, a classic escalation path works like this: an identity has `iam:CreatePolicyVersion` permission. This allows it to create a new version of an existing managed policy. Policies can have up to five versions, and you can set any version as the default. So the attacker creates a new version of a policy attached to their own identity, writes `"Effect": "Allow", "Action": "*", "Resource": "*"` into it, and sets it as the default. They have just escalated to full administrative access using a permission that, on its face, looks like a routine IAM management capability.

There are dozens of these paths. `iam:AttachUserPolicy` lets you attach `AdministratorAccess` to yourself. `lambda:CreateFunction` combined with `iam:PassRole` lets you create a Lambda function that runs with a more privileged role than your own. `iam:CreateAccessKey` on another user lets you generate credentials for that user.

The mechanical point here is that **the IAM action namespace itself contains escalation primitives**. Any permission that allows an identity to modify its own permissions, modify other identities' permissions, or create new identities is an escalation risk. Least privilege means not just restricting access to data and compute resources, but restricting access to the permission system itself. This is the most commonly overlooked dimension, because IAM permissions don't feel like "real" access to engineers who are thinking about databases and buckets.

## Temporal Dimensions: Static Grants and Privilege Creep

Permissions are typically granted at a point in time for a specific reason and then never revisited. This creates **privilege creep** — the steady accumulation of permissions as an identity is granted access for each new task but never has old permissions revoked.

A service account created for a feature that shipped six months ago still has permissions for resources that feature no longer uses. An engineer who rotated off the infrastructure team still has their cluster-admin binding. A CI/CD pipeline that was once used to deploy to three environments still has credentials for an environment that was decommissioned. Each of these is a dormant permission — inactive, invisible, and available to anyone who compromises that identity.

The mechanical solution is **just-in-time (JIT) access**: instead of granting standing permissions, you grant temporary permissions that expire. An engineer who needs production database access gets a time-limited credential that is automatically revoked after an hour. A deployment pipeline assumes a role only for the duration of the deployment and the session expires when the job completes.

AWS implements this through STS (Security Token Service) sessions, where assumed roles produce temporary credentials with a configurable maximum duration. GCP has Conditional IAM Bindings that can include time-based conditions. HashiCorp Vault generates dynamic secrets — database credentials that Vault creates on demand, with a lease that Vault automatically revokes on expiration.

The tradeoff is real. JIT access requires infrastructure to manage the granting and revoking of access, it adds latency to workflows (you have to request and wait for access), and it creates a new failure mode: if the access-granting system is down, engineers with legitimate needs cannot do their work. This is the **"break glass" problem** — you need a fallback mechanism for emergencies, but that fallback mechanism is itself a standing privilege that undermines least privilege.

## Tradeoffs and Failure Modes

### Velocity vs. Constraint

The most common reason least privilege fails in practice is not ignorance — it's friction. Engineers hit a permissions error, they need to ship, and the fastest path is to widen the policy until it works. In AWS, this often means replacing a specific resource ARN with `*`, or replacing a list of specific actions with `s3:*` or `ec2:*`. These quick fixes are rarely reverted.

This is an organizational problem as much as a technical one. If requesting a scoped permission takes a ticket, a review, and three days, but adding `*` to a self-managed policy takes thirty seconds, the system's incentives point toward overpermissioning. Least privilege at scale requires that granting *correct* permissions is nearly as easy as granting *broad* permissions. This means investment in tooling: policy generators that analyze CloudTrail or audit logs to determine what permissions a workload actually uses, self-service portals that let teams request scoped access with automated approval for well-understood patterns, and IaC modules that encode least-privilege policies for common service patterns.

### The Audit Gap

Another failure mode is **policy-as-fiction**: the stated policies look correct, but the effective permissions diverge from what anyone believes they are. This happens when policies are managed through multiple systems (Terraform for some, console clicks for others, a custom script for legacy accounts), when resource-based policies grant access that doesn't show up in an identity-centric audit, and when cross-account trust relationships create paths that no single-account review can see. If you are only auditing identity policies attached to users and roles, you are seeing a fraction of the actual permission surface.

### Overly Tight Permissions as a Failure

There is a less-discussed failure mode: permissions that are *too* tight break incident response. If your on-call engineer does not have the ability to inspect logs, describe resources, or modify security groups during an active incident because those permissions were restricted to a narrow automation role, least privilege has become an obstacle to the very security outcome it was supposed to produce. The design must account for operational scenarios, not just steady-state behavior. This usually means pre-provisioned incident-response roles with elevated but audited access — not permanent admin credentials, but not zero standing access either.

## The Mental Model

Think of your infrastructure's permissions as a directed graph. Identities are nodes. Permissions are edges. Resources are nodes. Every edge is a path an attacker can traverse after compromising a single node. Least privilege is the discipline of minimizing the number of edges in this graph and minimizing the connectivity between high-value nodes.

The most important shift is moving from thinking about permissions as *individual policy documents* to thinking about them as a *system-wide reachability problem*. A policy is not secure or insecure in isolation — it is secure or insecure relative to every other policy, trust relationship, and resource configuration in the environment. The question is never "is this policy too broad?" in the abstract. The question is: "if the identity this policy is attached to is compromised, what can an attacker reach?"

This reachability framing is what makes least privilege operational rather than aspirational. It gives you a concrete thing to measure, a concrete thing to minimize, and a concrete thing to audit.

## Key Takeaways

- Permission evaluation in major cloud platforms uses layered intersection, not simple union — understanding that permission boundaries and SCPs act as ceilings on what identity policies can grant is essential to implementing architectural guardrails.

- Blast radius is a graph traversal: the reachable set of resources and identities from a compromised node, including transitive paths through role assumption, role passing, and cross-account trust.

- Privilege escalation is not a single exploit but a chain of individually authorized operations — any permission that allows modifying the permission system itself (creating policies, attaching policies, passing roles) is an escalation primitive that must be restricted with extreme care.

- Privilege creep — the accumulation of stale permissions over time — is the default state of any system without active permission lifecycle management; just-in-time access is the mechanical countermeasure but introduces its own operational dependencies.

- Least privilege fails most often not from ignorance but from friction: if granting broad access is faster than granting correct access, the system's incentives will produce overpermissioned environments regardless of policy.

- Auditing identity-based policies alone produces an incomplete picture; resource-based policies, cross-account trust relationships, and transitive permission paths must be included to understand actual effective access.

- Overly restrictive permissions that prevent incident response or operational debugging are a failure mode of least privilege, not a success — the design must include scoped, audited access for operational scenarios.

- The durable question to ask about any permission is not "is this policy minimal?" in isolation, but "if this identity is compromised, what is the full set of resources and actions an attacker can reach?"


[← Back to Home]({{ "/" | relative_url }})
