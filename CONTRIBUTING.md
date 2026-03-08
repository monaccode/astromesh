# Contributing to Astromesh

Astromesh, this repository, and the project materials included in it are
the property of Monaccode Technology LLC, except where third-party
components remain subject to their respective licenses and ownership.

Thank you for your interest in contributing to **Astromesh --- Agent
Runtime Platform**.

Astromesh is an open platform designed to build, orchestrate, and
operate AI agents at scale. We welcome contributions from developers,
researchers, and infrastructure engineers.

------------------------------------------------------------------------

# Ways to Contribute

You can contribute to Astromesh in many ways:

• Reporting bugs\
• Improving documentation\
• Submitting bug fixes\
• Adding new features\
• Improving performance\
• Creating examples or tutorials\
• Reviewing pull requests

------------------------------------------------------------------------

# Development Setup

Astromesh requires:

-   Python 3.12+
-   uv package manager

Install dependencies:

``` bash
uv sync
```

Install optional dependencies:

``` bash
uv sync --extra all
```

Run the development server:

``` bash
uv run uvicorn astromesh.api.main:app --reload
```

Run tests:

``` bash
uv run pytest
```

------------------------------------------------------------------------

# Branching Model

Main development branch:

    develop

Feature branches:

    feature/<feature-name>

Bug fixes:

    fix/<issue-name>

------------------------------------------------------------------------

# Commit Convention

Astromesh follows **Conventional Commits**.

Examples:

    feat: add vector memory backend
    fix: resolve websocket connection leak
    docs: update runtime architecture docs
    refactor: simplify model router logic
    test: add coverage for memory manager

------------------------------------------------------------------------

# Pull Request Process

1.  Fork the repository
2.  Create a feature branch
3.  Write tests when applicable
4.  Ensure all tests pass
5.  Open a Pull Request

Pull requests should include:

• Description of the change\
• Motivation and context\
• Related issue (if applicable)

------------------------------------------------------------------------

# Code Style

We use:

• **ruff** for linting\
• **ruff format** for formatting

Run before submitting:

``` bash
ruff check .
ruff format .
```

------------------------------------------------------------------------

# Documentation

Documentation lives in:

    docs/

If you introduce new functionality, please update or add documentation.

Important documentation includes:

-   architecture.md
-   configuration-guide.md
-   whatsapp-integration.md

------------------------------------------------------------------------

# Community

We aim to build a collaborative and welcoming community.

Please follow our **Code of Conduct**.
