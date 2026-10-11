---
type: Metric
title: Revenue
description: Recognized revenue for a fiscal year.
tags: [finance, revenue]
owner: finance
resource: https://wiki.acme/finance/revenue
generated: { by: reference_agent/gemini-2.5-pro, at: 2026-06-20T22:53:05Z }
verified:
  - { by: process:finance-nightly, at: 2026-06-26T02:00:00Z }
stale_after: 2099-01-01T00:00:00Z
sources:
  - id: rev-policy
    resource: https://wiki.acme/finance/revenue-recognition
    title: Revenue recognition policy
---

# Definition

Sum of `amount` over [orders](/tables/orders.md) booked to the fiscal year.[^rev-policy]

[^rev-policy]: Revenue recognition policy
