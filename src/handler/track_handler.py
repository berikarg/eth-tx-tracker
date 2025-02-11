from fastapi import APIRouter
from src.models.track_request import TrackRequest
from src.service.track_service import TrackService

def create_track_router(track_service: TrackService) -> APIRouter:
    router = APIRouter()

    @router.post("/track", tags=["Tracking"], summary="Create a new tracking request")
    async def track_transaction(req: TrackRequest):
        """
        Registers a request to track an incoming transaction.
        """
        track = await track_service.create_track(req)
        return {"status": "ok", "message": f"Tracking request for {track.address} registered"}

    @router.get("/tracks", tags=["Debug"], summary="List all tracking requests")
    async def list_tracks():
        """
        Returns all tracked items for debugging.
        """
        tracks = track_service.list_tracks()
        return [
            {
                "address": t.address,
                "contract_address": t.contract_address,
                "amount": str(t.amount),
                "decimals": t.decimals
            }
            for t in tracks
        ]

    return router