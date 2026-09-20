"""Console entry point for the internal engine service."""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run(
        "paper4_pipeline.web_api.app:app",
        host="127.0.0.1",
        port=8001,
        reload=False,
    )


if __name__ == "__main__":
    main()
