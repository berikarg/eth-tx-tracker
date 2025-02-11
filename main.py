import asyncio
import logging
import argparse

import yaml
from fastapi import FastAPI
from contextlib import asynccontextmanager
import uvicorn

from src.handler.track_handler import create_track_router
from src.repository.track_repository import TrackRepository
from src.service.track_service import TrackService

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", help="path to yaml config", default="./configs/config.yml")
    args = parser.parse_args()
    with open(args.config, 'r') as file:
        config = yaml.safe_load(file)

    track_repository = TrackRepository()
    track_service = TrackService(track_repository, config["http_rpc_url"], config["ws_rpc_url"], logger)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        asyncio.create_task(track_service.start_block_listener())
        yield

    app = FastAPI(
        title="Ethereum Transaction Tracker",
        description="Service to track ETH and ERC-20 transactions.",
        version="1.0.0",
        lifespan=lifespan,
    )

    track_router = create_track_router(track_service)
    app.include_router(track_router)

    uvicorn.run(app, host=config["host"], port=config["port"])

if __name__ == "__main__":
    main()