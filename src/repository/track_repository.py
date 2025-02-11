from typing import List

from src.models.track import Track

class TrackRepository:
    def __init__(self):
        self._tracks: List[Track] = []

    def add_track(self, track: Track) -> None:
        self._tracks.append(track)

    def list_tracks(self) -> List[Track]:
        return self._tracks

    def remove_track(self, track: Track):
        self._tracks.remove(track)

