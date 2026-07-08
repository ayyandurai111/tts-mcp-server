#!/usr/bin/env python3
"""Entry point: run with `python run.py` (or via uvicorn CLI directly)."""

import uvicorn

from common.config import HOST, PORT

if __name__ == "__main__":
    uvicorn.run("api.app:app", host=HOST, port=PORT, reload=False)
