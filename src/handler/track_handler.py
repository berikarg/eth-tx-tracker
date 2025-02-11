from fastapi import APIRouter, HTTPException, status
from src.models.track_request import TrackRequest
from src.service.track_service import TrackService, TrackAlreadyExistsError

def create_track_router(track_service: TrackService) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/track",
        tags=["Tracking"],
        summary="Create a new tracking request",
        responses={
            200: {
                "description": "Tracking request successfully registered",
                "content": {
                    "application/json": {
                        "example": {
                            "status": "ok",
                            "message": "Tracking request for <address> registered"
                        }
                    }
                }
            },
            409: {
                "description": "Tracking request already exists",
                "content": {
                    "application/json": {
                        "example": {
                            "message": "Tracking request for address <address> amount <amount> contract <contract_address> already exists"
                        }
                    }
                }
            }
        }
    )
    async def track_transaction(req: TrackRequest):
        """
        Registers a request to track an incoming transaction.
        """
        try:
            track = await track_service.create_track(req)
        except TrackAlreadyExistsError as e:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=e.message
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e)
            )
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