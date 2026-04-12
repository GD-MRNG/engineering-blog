---
layout: post
title: "3.2.4 Static and Dynamic Analysis: SAST and DAST"
author: "Glenn Lum"
date:   2026-03-24 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most teams that run SAST and DAST treat them as two flavors of the same thing: security scanners. One runs "early" on source code, the other runs "late" against a deployed app, and together they "cover security." This framing is wrong in a way that matters. SAST and DAST are not two scanners doing the same job at different times. They operate on entirely different representations of your application, use fundamentally different detection techniques, and are blind to fundamentally different categories of vulnerability. A SQL injection that SAST catches trivially might be invisible to DAST. A server misconfiguration that DAST exposes in seconds is something SAST cannot even reason about. Understanding *why* requires looking at what each tool actually does when it runs.

## How Static Analysis Finds Vulnerabilities

A SAST tool never executes your code. It reads it. But "reads it" undersells the process. What a SAST tool actually does is parse your source code into a structured representation — typically an **abstract syntax tree (AST)** — and then builds several derived models from that tree: a **control flow graph** (what execution paths are possible), a **data flow graph** (how values move through the program), and a **call graph** (which functions call which other functions). The vulnerability detection happens against these models, not against raw text.

The most important technique in modern SAST is **taint analysis**. The tool defines a set of **sources** — places where untrusted data enters the program — and a set of **sinks** — places where data does something dangerous. It then traces whether tainted data from a source can reach a sink without passing through a **sanitizer** that neutralizes the danger.

Here is what that looks like concretely. Consider this Python endpoint:

```python
def search(request):
    query = request.GET.get('q')
    sql = "SELECT * FROM products WHERE name = '" + query + "'"
    cursor.execute(sql)
```

The SAST tool identifies `request.GET.get('q')` as a source — user-controlled HTTP input. It traces the value through the assignment to `query`, through the string concatenation into `sql`, and into `cursor.execute()`, which is a sink — a function that executes a SQL statement. No sanitizer (no parameterized query, no escaping function) appears on that path. The tool flags it.

This sounds simple, but the computational complexity escalates fast. In real codebases, tainted data does not flow in a straight line within a single function. It gets passed as arguments to other functions, stored in object attributes, serialized into data structures, and retrieved elsewhere. **Interprocedural analysis** — following data flow across function call boundaries — is where the quality gap between SAST tools lives. A tool that only does intraprocedural analysis (within a single function) will miss a vulnerability where `query` is passed to `build_sql(query)`, which returns a string later passed to `execute()` in a different module. A tool with deep interprocedural analysis will trace through both call sites. This is also where analysis time explodes: tracing data flow across an entire codebase's call graph is computationally expensive, and most tools make pragmatic tradeoffs about how many call levels deep they follow.

Below taint analysis, there is a simpler layer: **pattern matching**. This is closer to sophisticated grep. The tool has rules that flag specific code patterns — use of `MD5` for password hashing, hardcoded strings that look like API keys, calls to deprecated cryptographic functions. Pattern matching is fast and cheap but shallow. It catches known-bad patterns without understanding data flow. Most SAST tools use a combination of both techniques, with pattern matching handling the low-hanging fruit and taint analysis handling the deeper vulnerability classes.

A critical constraint: SAST is inherently **language-specific**. The parser, the AST construction, the understanding of framework conventions (what constitutes a "source" in Django versus Spring versus Express) — all of it must be built per language and often per framework. A SAST tool with excellent Java support may have shallow Python support. This is not a minor quality gap; it determines whether the tool can follow data flow through framework-specific patterns like middleware, decorators, or dependency injection.

## How Dynamic Analysis Finds Vulnerabilities

DAST operates from the opposite direction. It has no access to source code. It interacts with your application exclusively through its external interfaces — HTTP requests and responses, typically — the same way an attacker would.

A DAST scan proceeds in two phases. The first is **discovery**: the tool crawls the application, following links, submitting forms, calling API endpoints, and building a map of the attack surface. Every URL, query parameter, form field, HTTP header, and cookie it encounters becomes a potential injection point. Some tools also ingest OpenAPI or Swagger specifications to supplement crawling, which is particularly important for API-only services with no HTML to crawl.

The second phase is **attack generation and response analysis**. For each discovered input point, the tool sends a battery of crafted payloads drawn from known attack patterns. For SQL injection, it might send `' OR '1'='1`, `'; DROP TABLE users--`, or time-based payloads like `' AND SLEEP(5)--`. For cross-site scripting, it sends payloads like `<script>alert(1)</script>` or event handler injections. For path traversal, it tries `../../etc/passwd`.

After sending each payload, the tool analyzes the response. The detection logic varies by vulnerability class. For reflected XSS, the tool checks whether its injected script tag appears unescaped in the response body. For SQL injection, it looks for database error messages in the response, unexpected changes in response content (a query returning all records instead of zero), or — for blind injection — measurable differences in response time after a `SLEEP` payload. For security misconfigurations, it checks for missing headers (`Strict-Transport-Security`, `X-Content-Type-Options`), overly permissive CORS policies, or exposed server version strings.

This approach has a critical dependency: **DAST can only test what it can reach**. If the crawler cannot navigate to a particular page — because it requires a multi-step workflow, specific application state, JavaScript rendering the tool does not support, or authentication it was not given credentials for — that surface goes untested. Authenticated scanning requires providing the tool with valid credentials or session tokens, and even then, the tool can only exercise the permissions those credentials grant. An admin-only endpoint will not be tested unless the tool has admin credentials.

The output of DAST is also structurally different from SAST. When DAST finds a vulnerability, it can tell you *what* is exploitable and *where* the endpoint is, but it cannot tell you *which line of code* is responsible. It knows the building has a broken window; it does not know which subcontractor installed it.

## Where Each Approach Is Structurally Blind

The differences are not just about timing or convenience. They are about what is *possible* for each technique to observe.

### What SAST Cannot See

SAST operates on source code. It has no visibility into:

**Runtime configuration.** Your code might use parameterized queries everywhere, but if the web server is configured with directory listing enabled, or CORS is set to `*` in the deployment configuration (not in source code), or TLS is terminated incorrectly at the load balancer, SAST has nothing to analyze. These are properties of the running system, not the source.

**Emergent behavior from component interaction.** A microservice might be individually secure, but the way Service A calls Service B might create an authorization bypass — Service A forwards user input to Service B's internal API without re-validating authentication. SAST analyzes each codebase in isolation. It cannot reason about the composite behavior of a deployed system.

**Business logic flaws.** SAST looks for known vulnerability patterns. It does not understand what your application is *supposed* to do. An endpoint that allows any authenticated user to modify any other user's profile is a severe authorization flaw, but the code implementing it is syntactically normal — it reads a user ID from the request and updates a database row. There is no tainted data reaching a dangerous sink. There is just wrong logic.

### What DAST Cannot See

DAST operates on observable behavior from outside the application. It has no visibility into:

**Unreachable code paths.** An error handler that constructs a SQL query from exception data, an admin endpoint that is not linked from any page the crawler visits, a code path triggered only by a specific race condition — if DAST cannot reach it through its crawling and fuzzing, it does not exist from DAST's perspective. This is a significant gap: attackers with access to source code (or time to reverse-engineer behavior) can find and target these paths.

**Vulnerabilities that do not produce observable output differences.** A stored XSS payload that gets saved to the database but only rendered on a page the scanner never visits. A second-order SQL injection where the injected payload is stored and later executed in a different context. Blind vulnerabilities that do not manifest in the immediate HTTP response are hard for DAST to catch, though timing-based techniques partially address this.

**The actual code location.** DAST findings require a human to trace from the vulnerable endpoint back to the responsible code. In a large codebase, this triage step can be as expensive as the initial detection.

## IAST: The Hybrid Approach

**Interactive Application Security Testing (IAST)** attempts to bridge this gap by instrumenting the application at runtime. An agent is deployed inside the application (attached to the runtime or embedded as a library), and it observes data flow in real time as the application handles requests. When a DAST scan — or a QA test suite, or manual testing — sends a request, the IAST agent watches the user-controlled input flow through actual function calls, database queries, and file operations inside the running process.

This gives you DAST's ability to test the real running system combined with SAST's ability to pinpoint the exact code path involved. The tradeoff is operational: IAST requires an agent running inside your application, which introduces runtime overhead (typically 2–10% latency, though this varies), requires per-language agent support, and adds deployment complexity. It also only observes code paths that are actually exercised during testing — it does not analyze code paths that no test case triggers.

## Tradeoffs and Failure Modes

### False Positive Fatigue Kills SAST Programs

The most common way SAST fails in practice is not that it misses vulnerabilities — it is that it finds too many non-vulnerabilities. SAST tools, particularly those doing interprocedural taint analysis, are conservative by design. If the tool cannot prove that a sanitizer exists on a path, it flags it. But the sanitizer might exist in a way the tool does not recognize: a custom validation library, a framework-level middleware that the tool's rules do not model, or an input that is constrained by an upstream API gateway. The result is a high false positive rate — commonly 30–70% in untuned deployments.

Teams that deploy SAST without investing in tuning — suppressing known false positive patterns, writing custom rules for internal frameworks, triaging initial findings to establish a baseline — quickly hit a wall. Developers learn to ignore the tool's output. The security findings become noise. This is worse than not having the tool at all, because the organization now believes it has SAST coverage while in practice no one reads the results.

### DAST Coverage Depends on What You Feed It

DAST's effectiveness is bounded by its ability to discover and interact with your application's surface. A single-page application with a complex JavaScript frontend and a REST API behind authentication will have a very different DAST experience than a traditional server-rendered web application with HTML forms. If the DAST tool cannot render JavaScript, it will miss every API call the frontend makes. If it is not configured with authentication, it tests only the login page and public endpoints.

The failure mode here is teams running DAST in CI/CD against a staging environment, getting a clean scan, and concluding the application is secure — when the tool only tested 15% of the actual attack surface because it could not navigate the SPA's client-side routing or authenticate to reach the real functionality.

### The Checkbox Trap

The deepest failure mode is organizational. Compliance frameworks often require "static analysis" and "dynamic analysis." Teams deploy both tools, configure them minimally, pipe the results into a dashboard, and never act on the findings because the volume is unmanageable and no one owns the triage process. Both tools are running. Neither tool is providing security value. The checkboxes are checked.

This happens because the tools are treated as products that produce security, rather than as instruments that produce *signals* requiring human judgment, tuning, and process integration.

## The Mental Model

Think of SAST and DAST as two fundamentally different lenses on the same system. SAST examines the *structure* of your code — it can see every path, every branch, every possible flow of data, including paths that are rarely or never executed. Its power is breadth and its weakness is abstraction: it reasons about what *could* happen, not what *does* happen, and it cannot see anything outside the source code. DAST examines the *behavior* of your running system — it can find real, exploitable vulnerabilities and configuration flaws in the actual deployed environment. Its power is realism and its weakness is reach: it can only test what it can touch, and it cannot see the code behind the behavior.

Neither tool is a superset of the other. They are not redundant, and they are not interchangeable. The decision of which to invest in is not "which is better" but "which category of blindness is more dangerous for this system right now." For most production systems, the answer is that both categories of blindness are unacceptable, which is why mature security programs run both — but only get value from either when they invest in tuning, triage, and integration with developer workflows.

## Key Takeaways

- SAST works by building control flow and data flow models from source code and tracing tainted data from sources (user input) to sinks (dangerous operations) without sanitization — it does not pattern-match against raw text in any serious implementation.
- DAST works by crawling a running application, sending known attack payloads to every discovered input point, and analyzing responses for evidence of successful exploitation — it has zero knowledge of the underlying code.
- SAST is structurally blind to runtime configuration, component interaction behavior, and business logic flaws; DAST is structurally blind to unreachable code paths, second-order vulnerabilities, and the source code location of any finding.
- SAST false positive rates of 30–70% in untuned deployments are common, and the most frequent failure mode is teams ignoring output entirely due to noise — making tuning and triage a prerequisite for value, not an optimization.
- DAST coverage is bounded by what the tool can discover and authenticate to; running DAST against a modern SPA without JavaScript rendering support or valid credentials may cover a small fraction of the actual attack surface.
- IAST bridges the gap by instrumenting the runtime to observe real data flow during testing, but it introduces agent overhead, requires per-language support, and only covers code paths actually exercised by tests.
- The two tools cover fundamentally different attack surfaces — running both without tuning either produces compliance artifacts, not security; running one well-tuned tool produces more security value than running both poorly.
- The real cost of these tools is not licensing — it is the engineering time required to tune rules, triage findings, integrate results into developer workflows, and maintain coverage as the application evolves.

[← Back to Home]({{ "/" | relative_url }})
