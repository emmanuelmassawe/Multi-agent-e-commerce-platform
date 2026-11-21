.PHONY: bench bench-api
bench:
	uv run python benchmarks/run_fake_supervisor.py
	uv run python benchmarks/run_fake_agents.py
	uv run python benchmarks/run_retrieval.py --sizes 128 1024 --queries 32
	$(MAKE) bench-api

bench-api:
	uv run --locked python benchmarks/run_api_load.py --users 4 --seconds 15
