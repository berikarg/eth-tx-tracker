from typing import Set

from src.models.track import Track

class TrackRepository:
    def __init__(self):
        self._tracks: Set[Track] = set()

    def add_track(self, track: Track) -> None:
        self._tracks.add(track)

    def list_tracks(self) -> Set[Track]:
        return self._tracks

    def remove_track(self, track: Track) -> None:
        self._tracks.remove(track)
