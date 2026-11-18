# 0002. Python and FastAPI for the backend

- Status: proposed
- Date: 2026-11-18

## Context

The project instructions prescribe Python 3.12, FastAPI, Pydantic v2, and SQLAlchemy 2 async.

## Decision drivers

Compatibility with prescribed stack, typed validation, async HTTP support, and maintainability.

## Options considered

- Python 3.12 with FastAPI.
- A different language and HTTP framework, which would require an ADR to change the stated stack.

## Evidence

Stack constraint comes from project instructions. Comparative benchmarks are not measured yet.

## Decision

Record Python 3.12 and FastAPI as the prescribed direction, pending review.

## Consequences

The API scaffold uses FastAPI. ORM, migrations, and full validation policy are later-phase work.

