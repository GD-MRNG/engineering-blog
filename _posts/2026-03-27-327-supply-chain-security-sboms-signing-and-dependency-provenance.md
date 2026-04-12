---
layout: post
title: "3.2.7 Supply Chain Security: SBOMs, Signing, and Dependency Provenance"
author: "Glenn Lum"
date:   2026-03-27 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most teams that adopt SBOMs, artifact signing, and provenance checks treat them as compliance checkboxes — generate a document, slap a signature on an image, reference a SLSA level in a slide deck. The artifacts get produced but never consumed. The signatures exist but nothing verifies them in the critical path. The provenance attestations sit in a registry, unqueried. This is not supply chain security. It is supply chain theater. The gap between having these artifacts and actually using them to make trust decisions is where every real supply chain attack finds its opening. To close that gap, you need to understand what each mechanism actually proves, how it proves it, and where the proof falls apart.

## What an SBOM Actually Contains and How It Gets Built

An SBOM is not a dependency list. Your `package-lock.json` or `go.sum` is a dependency list. An SBOM is a structured, standardized document that describes every component in a built artifact — direct dependencies, transitive dependencies, the compiler or runtime used, embedded libraries, vendored code, even operating system packages in a container image — along with metadata about each component's origin, version, and licensing.

Two formats dominate: **SPDX** (an ISO standard, originating from the Linux Foundation) and **CycloneDX** (from OWASP). They encode similar information differently. SPDX models components and relationships as a graph with explicit relationship types (`DEPENDS_ON`, `BUILD_TOOL_OF`, `CONTAINED_BY`). CycloneDX uses a more hierarchical component inventory model with explicit vulnerability and service extensions. Neither is strictly superior; SPDX has deeper roots in license compliance, CycloneDX in security-oriented tooling. The choice matters less than consistency — pick one and make sure your entire toolchain can produce and consume it.

The critical question is *when* the SBOM is generated, because this determines its accuracy.

**Source-level analysis** inspects manifest files (`pom.xml`, `requirements.txt`, `Cargo.toml`) and produces an SBOM from declared dependencies. This is fast and cheap but misses everything the build process introduces: dependencies resolved at build time, C libraries linked during compilation, packages pulled into a container base image. It also trusts the manifest, which may not reflect what actually gets built.

**Build-time generation** hooks into the actual build process — the resolver, the compiler, the linker — and records what was actually consumed. Tools like Syft operating on a built container image, or build systems that emit provenance during the build, produce SBOMs that reflect the real artifact. This is more accurate but requires integration with your build pipeline and introduces a dependency on the SBOM tooling itself.

**Binary analysis** reverse-engineers components from a compiled artifact by scanning for known library signatures, version strings, and file hashes. This is the most honest — it looks at what you actually ship — but it is the least complete. Statically linked libraries, minified JavaScript, and vendored Go modules can all evade detection.

Each component in the SBOM needs a stable, unambiguous identifier. This is where **Package URL (purl)** comes in — a standardized format like `pkg:npm/%40angular/core@16.2.0` that uniquely identifies a package across ecosystems. Without stable identifiers, correlating SBOM entries against vulnerability databases (which track CVEs by package identifier) becomes string-matching guesswork. The identifier scheme is not a cosmetic detail; it is what makes an SBOM queryable rather than merely readable.

## How Artifact Signing Actually Works

Signing a software artifact is cryptographically straightforward in principle: hash the artifact, encrypt the hash with a private key, distribute the public key so consumers can verify. In practice, the entire difficulty lives in key management and trust establishment.

**Traditional signing** uses long-lived key pairs. You generate a GPG or PGP key, guard the private key, publish the public key, and sign every release. The consumer imports your public key and verifies signatures before using your artifact. This works, but it creates brutal operational problems. The private key becomes a high-value target that must be secured indefinitely. If it is compromised, every artifact ever signed with it becomes suspect. Key rotation requires coordinating with every consumer. Key distribution itself is a trust problem — how does a consumer know the public key they fetched is actually yours?

**Sigstore** was created to solve these problems, and its architecture is worth understanding because it reframes signing around short-lived identity rather than long-lived keys.

Sigstore has three components. **Fulcio** is a certificate authority that issues short-lived signing certificates. Instead of managing your own key pair, you authenticate via an OIDC identity provider (your GitHub identity, your Google Workspace account, a Kubernetes service account). Fulcio verifies your identity, generates an ephemeral key pair, binds the public key to your verified identity in a short-lived certificate (typically valid for 10 minutes), and returns it. You sign your artifact with the ephemeral private key, then the private key is discarded.

**Rekor** is an immutable transparency log. After signing, the signature and the signing certificate are recorded in Rekor. This log is append-only and publicly auditable. It serves the same role as Certificate Transparency logs in the TLS ecosystem: even if a certificate was mis-issued, the public record makes it detectable.

**Cosign** is the client tool that orchestrates this. When you run `cosign sign`, it handles the OIDC flow, gets the Fulcio certificate, signs the artifact, and records the entry in Rekor. When a consumer runs `cosign verify`, it checks the signature against the certificate, checks the certificate against Fulcio's root of trust, and checks that the signing event exists in Rekor's transparency log.

The verification step is doing something subtle: it is not just checking that the artifact was not tampered with. It is checking *who signed it* (the OIDC identity bound to the certificate), *when they signed it* (the Rekor timestamp, which must fall within the certificate's validity window), and *whether that signing event was publicly recorded* (the transparency log entry). This is a fundamentally stronger statement than "someone with access to a particular private key signed this."

For container images specifically, signatures and attestations are stored as OCI artifacts in the same registry as the image itself, referenced by digest. This means your verification policy can be enforced at the admission control layer — a Kubernetes admission controller like Sigstore's Policy Controller or Kyverno can reject any image that lacks a valid signature from an expected identity before it ever runs in your cluster.

## Provenance Attestations and What They Prove

Signing tells you *who* produced an artifact. Provenance tells you *how* it was produced. These are different questions, and conflating them is a common mistake.

A **provenance attestation** is a signed statement describing the build process that created an artifact. The **SLSA framework** (Supply-chain Levels for Software Artifacts) defines increasingly rigorous levels of provenance:

At SLSA Build L1, the provenance simply documents the build process — which build system, which entry point, which inputs. At L2, the provenance is generated by a hosted build service (not the developer's laptop) and the provenance document is authenticated. At L3, the build service is hardened — the build runs in an isolated, ephemeral environment, and the provenance cannot be forged by the build's own tenants.

The concrete output is an **in-toto attestation** — a JSON document following the in-toto attestation framework, signed by the build system, that specifies the artifact's digest, the source repository and commit, the build configuration used, and the builder identity. Here is a simplified provenance predicate:

```json
{
  "buildType": "https://github.com/slsa-framework/slsa-github-generator/generic@v1",
  "builder": {
    "id": "https://github.com/slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@refs/tags/v1.9.0"
  },
  "invocation": {
    "configSource": {
      "uri": "git+https://github.com/my-org/my-repo@refs/tags/v2.1.0",
      "digest": { "sha1": "abc123..." },
      "entryPoint": ".github/workflows/release.yml"
    }
  },
  "materials": [
    {
      "uri": "pkg:npm/lodash@4.17.21",
      "digest": { "sha256": "def456..." }
    }
  ]
}
```

What this proves, when verified, is that a specific build system processed a specific source commit using a specific workflow and produced the artifact you are about to deploy. A policy engine can then enforce rules like: "only deploy artifacts built by our CI system from our main branch, built using our approved workflow file." This is a much stronger guarantee than signature alone, because it closes the gap between "a trusted identity signed this" and "this was built in a process we control."

GitHub Actions, for instance, can generate SLSA L3 provenance using the `slsa-github-generator` reusable workflows. The provenance is generated by an isolated builder workflow that the calling workflow cannot tamper with, and it is signed using Sigstore's keyless signing bound to the workflow's identity.

## Where This Breaks Down

**SBOMs without consumption infrastructure are inert.** The most common failure mode is generating SBOMs because a regulation or customer contract requires it, then storing them in a bucket where nothing reads them. An SBOM only creates value when it is ingested by a system that can correlate its contents against a continuously updated vulnerability database and alert when a newly disclosed CVE matches a component you ship. Without that pipeline — SBOM generation, storage, ingestion, correlation, alerting — the SBOM is a PDF you hand to an auditor.

**Signing without verification policy is security decoration.** If nothing in your deployment path rejects unsigned or incorrectly signed artifacts, signatures are cosmetic. The verification must be enforced — typically at the admission controller in Kubernetes, or at the deployment step in your CD pipeline — and it must be enforced as a hard gate, not a warning. The number of organizations that sign every image and verify none of them is disturbingly high.

**Provenance verification is only as strong as your trust in the build system.** SLSA L3 requires that the build environment is hardened and that the provenance cannot be forged by the build's tenants. But if your build system is self-hosted and an attacker gains access to the build infrastructure itself, they can forge provenance attestations. The trust boundary is the build system. If you do not control that boundary — or if you do but have not hardened it — your provenance guarantees are weaker than they appear.

**Transitive dependency opacity remains largely unsolved.** Your SBOM can enumerate that you depend on `libfoo@1.2.3`, and your signature can prove that `libfoo@1.2.3` was built by its maintainer. But unless `libfoo` itself has an SBOM and provenance attestation for *its* dependencies, you have a one-layer-deep view into a dependency tree that may be thirty layers deep. The chain of trust needs to be recursive, and the ecosystem tooling for recursive SBOM and provenance verification is still immature.

**The operational cost is real.** Maintaining SBOM generation across every build pipeline, keeping signing infrastructure operational, managing verification policies, updating vulnerability correlation databases, and responding to the alerts they generate all require dedicated effort. For small teams, the overhead may exceed the security value until dependency scale makes the risk concrete.

## The Model to Carry Forward

Think of supply chain security as three distinct questions about every artifact you run in production: *what is in it* (SBOM), *who produced it* (signing), and *how was it produced* (provenance). Each question has a different mechanism, a different verification path, and a different failure mode. None of them substitute for the others.

The underlying principle is that trust must be *verifiable and automated*. A human reviewing a dependency list is not supply chain security. A policy engine that rejects an image because its provenance attestation does not match your build policy, before the image ever reaches a node — that is supply chain security. The shift is from trust-by-default to trust-by-evidence, where every artifact must present cryptographically verifiable evidence of its composition, origin, and build process, and that evidence is checked in the critical deployment path with no human in the loop.

## Key Takeaways

- An SBOM is only useful when paired with a consumption pipeline that correlates its contents against vulnerability databases and triggers alerts on match — generating it without ingesting it is compliance theater.
- Build-time SBOM generation is more accurate than source-level analysis because it captures what was actually resolved and linked, not just what was declared in a manifest.
- Sigstore's keyless signing model eliminates long-lived key management by binding ephemeral signing certificates to verified OIDC identities and recording signing events in an immutable transparency log.
- Artifact signing proves who produced an artifact; provenance attestations prove how it was produced — these answer different questions and enforce different policies.
- SLSA provenance levels are only meaningful when the build system itself is a hardened trust boundary; self-hosted CI without isolation gives you provenance documents without provenance guarantees.
- Verification must be enforced as a hard gate in the deployment path (admission controller, CD pipeline step), not as an optional check or logged warning.
- Transitive dependency chains are the weakest link: your supply chain visibility extends only as far as your dependencies themselves publish SBOMs and provenance, which today is rarely more than one level deep.
- Package URL (purl) identifiers are what make SBOMs queryable against vulnerability databases — without stable, cross-ecosystem identifiers, correlation degrades to unreliable string matching.

[← Back to Home]({{ "/" | relative_url }})
