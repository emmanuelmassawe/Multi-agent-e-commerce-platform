.PHONY: bench
bench:
	uv run python benchmarks/run_fake_supervisor.py
	uv run python benchmarks/run_fake_agents.py
	uv run python benchmarks/run_retrieval.py --sizes 128 1024 --queries 32
