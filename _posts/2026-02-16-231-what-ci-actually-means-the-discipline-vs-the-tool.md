---
layout: post
title: "2.3.1 What CI Actually Means: The Discipline vs the Tool"
author: "Glenn Lum"
date:   2026-02-16 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most teams that claim to practice Continuous Integration do not. They have a CI *tool* — GitHub Actions, Jenkins, CircleCI, GitLab CI — and they run builds automatically when code is pushed. They call this CI, and by doing so, they miss the entire point. The tool automates validation. It does not perform integration. Integration is the act of combining your work with everyone else's work on a shared mainline, and the word "continuous" means you do this multiple times per day, not once per feature, not once per sprint, and not whenever a pull request happens to get approved. The distinction between the tool and the discipline is not pedantic. It is the difference between solving the problems CI was designed to solve and reproducing them while believing you've solved them.

## What "Integration" Actually Means

The Level 1 post defined CI as integrating every developer's work into a shared mainline frequently. That definition is doing more work than it appears to. **Integration** here has a specific meaning: your code is merged into a single shared branch — mainline, trunk, `main` — where it coexists with the current work of every other developer on the team. Until that merge happens, your code is isolated. It might compile. It might pass tests. But it has not been integrated, because it has not been combined with the changes your teammates made while you were working.

This distinction matters because the problems CI was invented to solve are all caused by isolation. When two developers work on separate branches for a week, they are each making assumptions about the state of the codebase that diverge further with every commit. Developer A renames a method. Developer B adds new calls to that method under its old name. Both branches pass their tests. Neither developer has done anything wrong. But their work is incompatible, and the incompatibility is invisible until someone tries to merge. The longer both branches live, the more of these invisible incompatibilities accumulate.

Running a CI pipeline on each branch does not change this. The pipeline validates that branch A works in isolation and branch B works in isolation. It says nothing about whether A and B work together. That question is only answered at integration time — when both sets of changes exist on the same branch and the test suite runs against the combined result.

## Why Frequency Is the Core Mechanism

The central insight of CI is that **integration pain is nonlinear with respect to time**. A branch that lives for two hours produces trivial merge effort. A branch that lives for two days produces noticeable merge effort. A branch that lives for two weeks can produce merge conflicts that take longer to resolve than the feature took to build.

This nonlinearity comes from two sources. The first is textual conflict: the probability that two developers modify the same lines of code increases with the number of lines each developer has changed, which grows over time. The second — and more damaging — is **semantic conflict**: changes that don't produce a merge conflict in version control but are logically incompatible. Developer A changes the return type of a function from a nullable to a non-nullable. Developer B adds a null check on the return value of that function. Git will merge these cleanly. The code will compile. The null check is now dead code, and the behavioral assumption it represented has been silently violated. These conflicts do not show up as merge conflicts. They show up as bugs in production, sometimes weeks later.

The only reliable mechanism for catching semantic conflicts early is to reduce the time between integrations. If developers integrate to mainline multiple times per day, the window for divergence is measured in hours. Conflicts — both textual and semantic — are caught when the changeset is small enough to fit in a developer's working memory. The fix is usually obvious. When the window is measured in days or weeks, the conflict is entangled with dozens of other changes, and resolving it requires archaeology.

This is why the frequency requirement in CI is not aspirational. It is mechanical. The practice works *because* integrations are frequent. Reduce the frequency and you reintroduce the problem proportionally.

## What the Tool Does and Does Not Do

A CI tool does three things: it watches for triggers (a push, a merge, a pull request event), it executes a defined pipeline (build, test, lint, security scan), and it reports the result (pass or fail). This is automation of *validation*, and it is genuinely valuable. Without it, frequent integration would be impractical because nobody would manually run the full test suite ten times a day.

But the tool does not control *what* is being integrated or *how often*. If a team uses feature branches that live for a week and runs a CI pipeline on every push to those branches, the tool is validating isolated work. The pipeline is green. The team feels good. No integration has occurred. The CI tool is functioning exactly as configured. The problem is that the team has configured it to automate something that is not Continuous Integration.

This creates a specific, observable phenomenon: the pipeline passes consistently on feature branches, and then breaks on `main` after merge. If you have ever seen a team where `main` is frequently broken after merges — despite every PR showing a green build — you are looking at a team that has CI infrastructure without CI practice. The green build on the feature branch was a false assurance. It validated the branch in isolation, not the branch integrated with all concurrent work.

## The Structural Requirements of Real CI

If CI requires integrating to mainline multiple times per day, certain ways of working become structurally incompatible.

**Long-lived feature branches are incompatible with CI.** A branch that lives for more than a day is, by definition, not being continuously integrated. This is not a judgment about branch-based workflows in general — it is a mechanical consequence of the definition. You can have long-lived feature branches or you can have Continuous Integration. You cannot have both. Teams that want CI end up practicing some form of **trunk-based development**, where developers commit to `main` directly or merge very short-lived branches (hours, not days) into `main`.

**Integrating incomplete work requires feature flags.** If you merge to mainline multiple times a day, you will merge code that is part of a feature that is not yet complete. Users cannot see half-finished features, so the code must be present in the codebase but inactive in the running application. **Feature flags** — runtime toggles that control whether a code path is executed — are the standard mechanism for this. This is a real cost of CI. You now need feature flag infrastructure, and you need the discipline to remove flags when features are complete. Stale feature flags are a well-known source of accidental complexity.

**Small, incremental changes are a prerequisite, not a preference.** CI does not work if developers build an entire feature in isolation and then integrate it as a single large changeset. The practice requires decomposing work into small, independently safe increments that can be merged without breaking the build. This is a design skill. It requires thinking about how to structure changes so that partially-complete work does not destabilize the system. It is one of the hardest parts of CI to adopt because it changes how developers think about their work, not just how they use their tools.

## The Pull Request Tension

Most teams today use pull requests as the primary mechanism for code review and collaboration. PRs create an inherent tension with CI because they introduce a delay between when code is written and when it is integrated.

Here is the typical flow: a developer finishes work on a branch, opens a PR, waits for review (hours to days), addresses review feedback (more hours), waits for re-review, then merges. If this cycle takes two days — which is optimistic for many teams — the developer is integrating once every two days. This is not continuous.

This does not mean pull requests are wrong. Code review has real value. But teams practicing real CI handle this tension deliberately rather than ignoring it. The common approaches are:

**Keep PRs extremely small.** A PR that changes 30 lines can be reviewed in five minutes. A PR that changes 500 lines sits in a review queue for a day. Small PRs are the single most effective lever for reconciling code review with integration frequency.

**Pair programming as synchronous review.** If two developers write the code together, the review has already happened at the time of writing. The code can be merged immediately. This eliminates the async review delay entirely, at the cost of requiring synchronous collaboration.

**Stacked PRs.** The developer continues working on subsequent changes while the first PR is in review, with each change building on the previous one. This keeps the developer productive, but it introduces complexity in managing the dependency chain between PRs.

**Post-commit review.** Some organizations — most famously Google — review code after it has been committed to the mainline. This maximizes integration frequency but requires high trust and a strong testing culture, because broken code can reach mainline before a human reviews it.

Each of these approaches has real costs. There is no configuration that gives you thorough async code review, single-developer feature branches, and continuous integration simultaneously. Teams must choose which constraints they are willing to relax.

## CI Theatre

**CI theatre** is the state where a team has the infrastructure of CI — the tool, the pipelines, the green badges in the README — without the practice. It is widespread and it is corrosive because it satisfies the organizational checkbox ("Do we have CI? Yes.") while delivering none of the benefits.

The most common pattern is straightforward: the team uses feature branches that live for days or weeks. A CI tool runs on every push. All builds pass. At the end of the sprint, branches are merged. Merge conflicts erupt. Integration bugs surface. The team spends the first days of the next sprint stabilizing `main`. This is the exact problem CI was designed to eliminate, occurring on a team that believes it practices CI.

A subtler pattern is **green-main theatre**: the team merges to `main` somewhat frequently, but the test suite is so thin that the build is trivially green. The pipeline runs, everything passes, but the tests are not validating integration. They are validating syntax. Semantic conflicts pass through undetected. The team has integration frequency but not integration *validation*, which is half the equation.

Another variant is the **always-broken main**. The team merges frequently, but nobody treats a broken `main` build as urgent. Failures stack up. Developers stop trusting the pipeline and start ignoring red builds. Within weeks, the team has lost the ability to distinguish a real failure from background noise. This is not a tool failure. It is a cultural failure to enforce the most important rule of CI: **a broken build on mainline is the team's highest-priority problem until it is fixed.**

## The Mental Model

CI is an **integration frequency discipline** that uses automation to make high frequency practical. The tool is the automation layer. The discipline is the decision to keep the window of isolation as small as possible — hours, not days — so that conflicts are caught when they are small, cheap, and easy to understand.

If you take one thing from this post, take this: the next time you evaluate whether a team is doing CI, do not ask what CI tool they use. Ask how long their branches live before merging to mainline. Ask what happens when the mainline build breaks. Ask how a half-finished feature reaches mainline safely. The answers to those questions tell you whether CI is being practiced. The tool tells you nothing.

## Key Takeaways

- **CI is defined by integration frequency, not by the presence of a CI tool.** If developers are not merging to a shared mainline multiple times per day, they are not practicing Continuous Integration regardless of what automation is in place.

- **Integration pain grows nonlinearly with branch lifetime.** A branch that lives for a week does not produce five times the merge difficulty of a branch that lives for a day — it produces far more, because semantic conflicts compound in ways that textual diffs do not reveal.

- **A CI pipeline running on a feature branch validates isolation, not integration.** The pipeline confirms that the branch works alone. It says nothing about whether the branch is compatible with concurrent work happening on other branches.

- **Long-lived feature branches and CI are structurally incompatible.** This is not a preference or a style choice — it is a consequence of what "continuous" means. Teams that want CI must move toward trunk-based development or very short-lived branches.

- **Real CI requires supporting practices: feature flags for incomplete work, small incremental changes, and a cultural commitment to fixing broken mainline builds immediately.** The discipline is not just about merging frequently — it is about making frequent merging safe.

- **Pull request workflows create inherent tension with CI** because they introduce a delay between writing code and integrating it. Teams must deliberately manage this tension by keeping PRs small, using synchronous review, or adopting post-commit review.

- **CI theatre — having the tool and infrastructure without the discipline — is worse than having no CI at all,** because it creates a false sense of safety while reproducing the exact integration problems CI was designed to solve.

- **To evaluate whether a team practices CI, ask how long branches live before merging, what happens when mainline breaks, and how incomplete features are handled.** These questions reveal the discipline. The tool choice is irrelevant.

[← Back to Home]({{ "/" | relative_url }})
