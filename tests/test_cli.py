from people_agent_mesh.cli import run_demo, run_evals


def test_cli_run_evals() -> None:
    # Executes without raising SystemExit or errors
    run_evals()


def test_cli_run_demo() -> None:
    # Executes end-to-end demo without error
    run_demo()
