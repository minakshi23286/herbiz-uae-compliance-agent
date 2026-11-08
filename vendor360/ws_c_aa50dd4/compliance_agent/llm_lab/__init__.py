"""HerBiz: LLM experiment lab (off by default, synthetic questions only).

Nothing in the live app imports this package. It reads the main database read-only and writes only to its own
experiment database. Runs need ANTHROPIC_API_KEY in the environment and the project-only `.venv-llm`.
"""
