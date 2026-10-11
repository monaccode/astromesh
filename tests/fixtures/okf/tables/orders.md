---
type: BigQuery Table
title: Orders
description: One row per completed order.
resource: https://console.cloud.google.com/bigquery?p=acme&d=sales&t=orders
tags: [sales, orders]
verified: { by: human:ana, at: 2026-06-25T09:00:00Z }
---

# Schema

| Column | Description |
|---|---|
| `total_usd` | Feeds [revenue](/metrics/revenue.md). |

# Notes

Margin is defined in [gross margin](../metrics/gross-margin.md); all metrics live in
[the metrics folder](/metrics/). Customers are described in
[customers](/tables/customers.md), which is not written yet. Upstream docs:
[export](https://example.com/orders). Back to the [table list](index.md).
See also [revenue again](/metrics/revenue.md), [this section](#schema),
[a secret](../../outside.md) and ![diagram](diagram.png).
