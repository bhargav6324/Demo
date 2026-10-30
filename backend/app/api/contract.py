"""Export the implemented API; compatibility entry point for existing tooling."""

from app.main import create_app


def create_contract_app():
    app = create_app()
    app.title = "Smart Library Backend - implementation contract"
    app.description = (
        "All 15 required operations are implemented. Phase 6 analytics/audit changes "
        "await independent tester validation. See docs/API_CONTRACT.md for behavior."
    )
    return app
