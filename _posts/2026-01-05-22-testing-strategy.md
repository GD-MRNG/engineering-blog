---
layout: post
title: "2.2 Testing Strategy"
author: "Glenn Lum"
date:   2026-01-05 11:00:00 +0800
categories: journal
tags: [Tier 2, Core Lifecycle Stages, Concept]
---

`[Tier 2, Core Lifecycle Stages, Concept]`

Testing is frequently discussed as a quality practice, but its primary operational function is something different: it is the mechanism that gives a team the confidence to deploy continuously. Without a reliable test suite, every deployment is a gamble. With one, deployment becomes a mechanical process with a known risk profile.

The **test pyramid** is the foundational mental model for thinking about testing strategy. At the base of the pyramid are **unit tests**: fast, isolated tests that validate the behavior of individual functions or classes in complete isolation from external dependencies like databases or network services. Unit tests should be numerous (hundreds or thousands) and should run in seconds. They are cheap to write and cheap to run, and they provide precise feedback about exactly which function is broken.

In the middle of the pyramid are **integration tests**: tests that validate how components interact with each other and with real external dependencies. An integration test might verify that your service can correctly write to and read from a database, or that two services communicate correctly across their API boundary. Integration tests are more expensive to run because they require real infrastructure (a test database, a test message queue), and they are slower. You should have fewer of them than unit tests, and they should focus on the interfaces and contracts between components, not the internal logic of each component.

At the top of the pyramid are **end-to-end (E2E) tests**: tests that simulate a real user journey through the entire system, from the front end through every backend service to the database and back. E2E tests provide the highest confidence that the system works as a whole, but they are the slowest, most brittle, and most expensive tests to write and maintain. They should be reserved for the most critical user journeys (checkout, authentication, core data flows) and kept to a minimum. The pyramid shape is prescriptive: many unit tests, fewer integration tests, very few E2E tests.

**Contract testing** addresses a specific problem in microservices architectures that the test pyramid doesn't solve. If Service A calls Service B, you want to verify that the interface between them hasn't broken. But running both services together for this verification is expensive and slow. Contract testing solves this by defining the "contract" (the expected request and response format) between the two services and verifying that each service independently satisfies the contract. If Service B changes its API in a way that breaks Service A's contract, the contract test fails immediately, without requiring both services to be deployed and running together.

**Performance and load testing** validate that the system behaves correctly not just functionally but under realistic conditions of concurrent usage. A service might pass all unit and integration tests and then fail completely when a hundred users hit it simultaneously because of an undetected database connection pool exhaustion or a memory leak that only manifests under sustained load. Performance tests establish baselines (what is the expected latency and throughput of this service under normal conditions?) and regression gates (if the latest change increases p99 latency by more than 10%, fail the pipeline).

The operational consequence of your testing strategy is the speed of your feedback loop. If your CI pipeline takes forty-five minutes to complete, developers will batch their commits, accumulate changes, and introduce larger, harder-to-debug changesets. A well-designed testing strategy, one that runs fast unit tests first, runs slower integration tests only on changes that affect integration points, and reserves E2E tests for pre-production gates, can keep the feedback loop under ten minutes and make continuous integration behaviorally realistic rather than aspirationally nominal.