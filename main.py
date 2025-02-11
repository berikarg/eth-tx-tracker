import asyncio
import logging
import os

from fastapi import FastAPI
from contextlib import asynccontextmanager
import uvicorn

from src.handler.track_handler import create_track_router  # <-- changed import
from src.repository.track_repository import TrackRepository
from src.service.track_service import TrackService

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    track_repository = TrackRepository()

    eth_rpc_url = os.getenv("ETH_RPC_URL", "https://sepolia.infura.io/v3/c05e8158ffb24160aa5a9d212e56223e")
    track_service = TrackService(track_repository, eth_rpc_url, logger)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        asyncio.create_task(track_service.start_block_listener())
        yield

    app = FastAPI(
        title="Ethereum Transaction Tracker",
        description="Service to track ETH and ERC-20 transactions.",
        version="1.0.0",
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    track_router = create_track_router(track_service)
    app.include_router(track_router)

    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)

if __name__ == "__main__":
    main()