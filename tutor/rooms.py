"""Stand-ins for the door and the room until a real room exists."""

from __future__ import annotations

from tutor.grading import DoorOrder, RoomResult, Submission


class NullDoor:
    """No private door is needed: the room has no network of its own."""

    def start_create(self, order: DoorOrder) -> str:
        return "no-door"

    def status(self, endpoint_id: str) -> str:
        return "available"

    def delete(self, endpoint_id: str) -> None:
        return None


class UngradedRoom:
    def grade(self, submission: Submission) -> RoomResult:
        return RoomResult.NOT_GRADED
