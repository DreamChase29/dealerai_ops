from fastapi import FastAPI

from dealerai_ops.main import create_app


def test_application_imports_successfully() -> None:
    app = create_app()

    assert isinstance(app, FastAPI)
