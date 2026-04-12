---
layout: post
title: "2.4.6 Supply Chain Security: Why Your Dependencies Are Your Attack Surface"
author: "Glenn Lum"
date:   2026-02-26 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers, when they hear "supply chain security," think about running a vulnerability scanner in CI. That is the equivalent of checking whether your front door lock has a known defect while leaving every window open. Vulnerability scanning catches *known* problems in *known* dependencies. The supply chain attacks that made headlines — SolarWinds, event-stream, ua-parser-js, Codecov — were not known vulnerabilities at the time of exploitation. They were trusted code that became malicious, or trusted infrastructure that was silently compromised. The scanner had nothing to match against because no advisory existed yet.

The Level 1 post covered *what* these mitigations are: vulnerability scanning, integrity verification, artifact provenance. This post is about *how* each of those mechanisms actually works, what they can and cannot prove, and where the gaps between them create real exposure.

## How Your Dependency Graph Becomes a Trust Graph

When your application declares a dependency, your package manager resolves that dependency, then resolves *its* dependencies, recursively, until the entire tree is complete. A moderately complex Node.js application routinely pulls in 800 to 1,500 transitive packages. A Java application using Spring Boot can easily exceed 200 transitive JARs. You probably reviewed the five or ten libraries you chose directly. You almost certainly did not review the hundreds of packages those libraries pulled in.

Each node in that dependency tree represents a piece of code that will execute with the full privileges of your application. If your web server depends on a logging library that depends on a string formatting utility maintained by a single developer with a Gmail account and no two-factor authentication enabled — that developer's account security is now part of your application's security posture. The dependency graph is a trust graph, and you are trusting every node in it.

### The Ways That Trust Gets Exploited

Supply chain attacks are not a single technique. They are a category, and the attack vectors are mechanically distinct.

**Typosquatting** exploits the moment a developer types a package name. An attacker publishes `lodsah` or `reqeusts` to a public registry, containing malicious code. If a developer miskeys the name in their manifest file or install command, the malicious package installs and runs. Registries have started adding detection for this, but coverage is inconsistent and reactive.

**Dependency confusion** exploits how package managers resolve names when both a private registry and a public registry are configured. If your company has an internal package called `auth-utils` and an attacker publishes `auth-utils` on the public npm or PyPI registry with a higher version number, many package manager configurations will prefer the public, higher-versioned package. The attacker's code now runs in your build. This is not a misconfiguration — it is the *default behavior* of several package managers when scoping and priority rules are not explicitly set.

**Maintainer takeover** is the attack class that caused the event-stream incident. A legitimate, widely-used package is maintained by someone who has lost interest. An attacker offers to take over maintenance, is given publish rights, and pushes a new version containing malicious code. Every downstream consumer who runs `npm update` or whose version range accepts the new release inherits the payload. The package remains legitimate in every metadata sense — same name, same registry, valid signature if the new maintainer signs it.

**Build infrastructure compromise** is what happened with SolarWinds and Codecov. The source code of the target project is never modified. Instead, the attacker compromises the build system or CI pipeline so that the artifact produced differs from what the source code specifies. The resulting binary or container image contains malicious code, but anyone reviewing the source repository sees nothing wrong. This is the hardest class to detect because it breaks the assumption that the artifact is a faithful representation of the source.

## What Software Composition Analysis Tools Actually Do

An **SCA tool** performs a specific sequence of operations, and understanding that sequence reveals both its power and its limits.

First, the tool constructs your dependency graph. It does this by parsing your manifest files (`package.json`, `pom.xml`, `go.mod`, `requirements.txt`) and, critically, your lock files. The lock file is where the exact resolved versions live. Without a lock file, the tool either performs its own resolution (which may not match your build) or works only with declared ranges, which is significantly less precise.

Second, the tool identifies each component using a standard naming scheme. The two dominant ones are **CPE** (Common Platform Enumeration), used by the National Vulnerability Database, and **PURL** (Package URL), which is more granular and maps cleanly to package manager ecosystems. A PURL looks like `pkg:npm/lodash@4.17.20` — it encodes the ecosystem, package name, and exact version in a single identifier. The quality of this identification step matters enormously. If the tool misidentifies a component or fails to map it to the correct CPE, the vulnerability lookup produces false negatives.

Third, the tool queries one or more vulnerability databases. The NIST National Vulnerability Database (NVD) is the canonical source, but its coverage lags — sometimes by days, sometimes by weeks after a vulnerability is disclosed. The GitHub Advisory Database (GHSA) and the OSV (Open Source Vulnerabilities) database often have faster coverage for ecosystem-specific issues. A good SCA tool queries multiple databases and cross-references results.

What comes back is a list of known CVEs mapped to specific package versions. This is where most teams stop, and where the meaningful limitations begin.

### The Reachability Problem

A CVE in a dependency means a vulnerability exists in that package's code. It does not mean your application is exploitable. If the vulnerable function is in a code path your application never invokes — because you use a different subset of the library's API — the vulnerability exists in your dependency tree but is not reachable from your application. Advanced SCA tools attempt **reachability analysis**: they trace call graphs from your application code into the dependency to determine whether the vulnerable code path is actually exercised. This is computationally expensive, language-dependent, and imperfect (dynamic dispatch, reflection, and runtime code generation all confound static analysis). But even imperfect reachability analysis dramatically reduces false positives. Without it, teams drown in alerts for vulnerabilities that do not affect them, which leads to alert fatigue, which leads to real vulnerabilities being ignored.

### The Temporal Gap

SCA tools match against *known* vulnerabilities. Between the moment an attacker introduces malicious code and the moment that code is identified and cataloged as a CVE, the SCA tool reports nothing. For the event-stream attack, the malicious code was present for over two months before discovery. For less prominent packages, it can be much longer. SCA is a retrospective control. It catches yesterday's compromises, not today's.

## What SBOMs Contain and What They Enable

A **Software Bill of Materials** is a structured inventory of every component in an artifact. The two dominant formats are **SPDX** (maintained by the Linux Foundation) and **CycloneDX** (maintained by OWASP). Both are machine-readable (JSON, XML, or tag-value). They record package names, versions, supplier information, license data, and relationships between components (this package depends on that package).

SBOMs can be generated in several ways, and the method determines accuracy. **Build-time generation** instruments the build process itself and captures exactly what the build tool resolved. This is the most accurate method. **Manifest parsing** reads lock files and dependency declarations after the fact — accurate for declared dependencies but may miss vendored code, copy-pasted files, or statically linked C libraries that do not appear in a manifest. **Binary analysis** examines a compiled artifact and attempts to identify embedded components by matching code patterns or metadata — useful for compiled languages but inherently less precise.

The value of an SBOM is not in its generation. It is in what happens downstream. With a machine-readable inventory of every component in every deployed artifact, you can answer questions that are otherwise nearly impossible at scale: "Are we running any version of `log4j` anywhere?" becomes a database query instead of a multi-day firefight. When a new critical CVE drops, you can correlate it against every SBOM in your fleet and know within minutes which services are affected. This was the operational crisis that Log4Shell exposed — most organizations had no fast way to answer that question.

SBOMs also enable **policy enforcement at ingestion boundaries**. An artifact registry can reject any artifact whose SBOM contains a component with a critical unpatched CVE, a component with a disallowed license, or a component without a minimum provenance attestation. This shifts enforcement from "someone should check this" to "the system will not permit this."

## What Signing and Provenance Actually Prove

Code signing uses asymmetric cryptography to bind an identity to an artifact. When a maintainer signs a package, they produce a signature that proves two things: the artifact was signed by the holder of that private key, and the artifact has not been modified since signing. This is **integrity** and **attribution**, not safety. A maintainer who has been socially engineered, or whose account has been taken over, will produce validly signed malicious artifacts.

**Sigstore**, the signing framework that has become the emerging standard for open-source ecosystems, addresses one of the historical barriers to signing: key management. Traditional signing requires developers to generate, store, and rotate long-lived private keys, which most do not do. Sigstore's **keyless signing** model uses short-lived certificates tied to an identity provider (like GitHub OIDC). The developer authenticates through their existing identity, receives a temporary certificate, signs the artifact, and the signing event is recorded in a tamper-evident transparency log called **Rekor**. There is no long-lived key to steal. Verification checks the transparency log to confirm the signature was valid at the time of signing.

**Provenance attestations** go further than signing. A provenance record answers: where was this artifact built, from what source, by what build system, with what parameters? The **SLSA framework** (Supply-chain Levels for Software Artifacts) defines increasing levels of build integrity. At SLSA Level 1, the build process documents provenance. At Level 2, provenance is generated by a hosted build service (not the developer's laptop). At Level 3, the build service is hardened and the provenance is non-falsifiable — the builder itself signs the attestation, and the builder's identity is independently verifiable. What this means concretely: at SLSA Level 3, even if an attacker compromises a maintainer's GitHub account, they cannot produce an artifact with valid provenance unless they also compromise the build service itself. The SolarWinds-class attack — compromising the build system — is precisely what SLSA Level 3 and above are designed to make detectable.

Provenance does not prove the source code is benign. It proves the artifact was built from *this specific source* by *this specific builder*. If the source itself is malicious (as in the event-stream attack), the provenance will be valid and the artifact will still be malicious. This is a feature, not a bug — it means provenance is the right tool for detecting build tampering, but you need other controls (code review, maintainer vetting, behavioral analysis) for detecting malicious source.

## Where This Breaks in Practice

**Alert fatigue is the dominant failure mode of SCA adoption.** A mature application with hundreds of transitive dependencies will produce dozens to hundreds of CVE findings on first scan. Many are in transitive dependencies the team did not choose and cannot easily replace. Many are not reachable. Without triage tooling, severity context, and reachability data, teams either ignore the results entirely or spend engineering cycles on changes that do not actually reduce risk.

**SBOMs that are generated but never consumed provide zero security value.** The executive mandate to "produce SBOMs" has outpaced the tooling and processes to use them. If no system is querying your SBOMs when new CVEs are published, if no policy engine is evaluating them at deployment gates, they are compliance artifacts, not security controls.

**Dependency pinning without update discipline creates a different risk.** Pinning every dependency to an exact version prevents surprise changes but also prevents automatic security patches. If your lock file is committed and never updated, you are frozen on a dependency tree that accumulates known vulnerabilities over time. The tradeoff is explicit: pinning gives you reproducibility and control, but it makes you responsible for actively monitoring and applying updates. Tools like Dependabot and Renovate automate the update proposal, but someone still has to review and merge.

**Signing without verification is security theater.** Many package registries now support signatures. Very few consumers verify them. If your `pip install` or `docker pull` does not check signatures against a trust policy, the presence of signatures in the ecosystem provides you no protection. Verification must be configured, enforced, and maintained — including decisions about which signing identities you trust, which is a policy problem more than a technical one.

## The Model to Carry Forward

Your dependency graph is an implicit trust delegation. Every edge in that graph is a decision — mostly made by someone else — to execute code from a source you have not audited, maintained by people you have not vetted, built by systems you do not control. SCA, SBOMs, and signing are three tools that answer three different questions. SCA asks: "Is any component in this graph known to be vulnerable?" SBOMs ask: "What exactly is in this artifact, and can I query that inventory at scale?" Signing and provenance ask: "Can I verify who built this artifact, from what source, and that it has not been tampered with?"

None of them answer the question "Is this code safe?" That question has no single tooling solution. What these mechanisms provide, together, is *evidence layering* — each one closes a category of attack that the others leave open. A mature supply chain security posture is not about choosing between them. It is about understanding which threat each one addresses, deploying them in the right order, and building the operational processes to act on what they tell you.

## Key Takeaways

- Your application's dependency graph is a trust graph — every transitive dependency is code that runs with your application's full privileges, maintained by people and systems outside your control.

- Supply chain attacks are not a single technique; typosquatting, dependency confusion, maintainer takeover, and build infrastructure compromise are mechanically distinct vectors that require different mitigations.

- SCA tools match your resolved dependency versions against vulnerability databases, but they only catch *known* vulnerabilities — the window between compromise and discovery is the attacker's advantage.

- Reachability analysis — determining whether your application actually invokes the vulnerable code path — is the difference between actionable SCA results and alert noise that gets ignored.

- SBOMs are only a security control if something downstream consumes them; an SBOM that is generated for compliance but never queried during incident response or policy enforcement provides no protection.

- Code signing proves integrity and attribution, not safety — a compromised maintainer will produce validly signed malicious artifacts, which is why provenance attestations (who built it, from what source, on what infrastructure) add a necessary additional layer.

- Dependency pinning trades the risk of unexpected changes for the risk of stale dependencies accumulating unpatched vulnerabilities; pinning without an active update process is not a security posture, it is a deferred liability.

- SCA, SBOMs, and signing each close a different category of supply chain risk — no single tool covers the full attack surface, and mature supply chain security requires all three working together with operational processes behind them.

[← Back to Home]({{ "/" | relative_url }})
