# Your agent goes here

This folder is empty on purpose.

We built the on-ramp: real organizations, an honest recipient corpus, a shelf-life clock, a
need signal, and a validation suite that tells you plainly whether any of it is wrong. We did
not build the vehicle. The design decisions in your agent are what you'll be judged on.

## What has to be true of what you build here

- **An ADK agent**, in Python.
- **At least one tool you built yourself.** A Python function tool, or one you defined in MCP
  Toolbox—either counts. The obvious candidate wraps your match query, but the more valuable
  one holds the logic that isn't a single query: composing the search string, applying the
  constraint filter, assembling the Match Brief. Consuming only prebuilt generic tools and
  calling that your design does not count.
- **At least one Google-managed MCP server, consumed.** Don't author your own—use BigQuery's
  built-in server or the [MCP Toolbox for Databases](https://github.com/googleapis/mcp-toolbox).
- **Deployed to Google Cloud**—Agent Runtime or Cloud Run, your choice.
- **Your required differentiator: BigQuery vector search.** Your agent must genuinely *call*
  the semantic search. Filtering on categories or `LIKE '%spinach%'` does not count, and it is
  the most common way a team misses the point while appearing to hit it.

## The thing worth remembering while you build

Vector search is a **candidate generator, not an answer**. There is at least one organization
in your corpus that semantically looks like a perfect match and physically cannot store the
food. What you do *after* the search—storage compatibility, pallet capacity, the pickup window
against the clock—is where this agent becomes useful instead of merely clever.

See the README for the four syntax traps, and Section 14 of the notebook for the query shape.
