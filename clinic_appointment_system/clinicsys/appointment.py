from dataclasses import dataclass
from enum import Enum

from . import config
from .errors import IllegalTransition, RuleViolation


class Status(Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


_LEGAL = {
    Status.PENDING: frozenset({Status.CONFIRMED, Status.CANCELLED}),
    Status.CONFIRMED: frozenset({Status.CANCELLED}),
    Status.CANCELLED: frozenset(),
}


@dataclass(frozen=True)
class AppointmentView:
    id: int
    patient_id: int
    staff_id: int
    start: int
    status: Status
    reason: str


# Invariants of Appointment:
#  1. id is a positive integer and never changes.
#  2. patient and staff are fixed when the appointment is created.
#  3. start is a whole hour from 0 to 167; the appointment occupies exactly [start, start + 1).
#  4. status is PENDING, CONFIRMED or CANCELLED and only moves
#     PENDING -> CONFIRMED, PENDING -> CANCELLED or CONFIRMED -> CANCELLED.
#  5. CANCELLED is final: a cancelled appointment never returns to another status.
#  6. A CONFIRMED appointment is never cancelled with less than 2 hours before start.
#  7. Once the clock reaches start, the status can no longer change.
#  8. A cancellation reason exists only while the status is CANCELLED.
class Appointment:
    def __init__(self, id, patient, staff, start):
        if id != int(id) or id <= 0:
            raise ValueError("appointment id must be a positive integer")
        if start != int(start) or not 0 <= start <= config.WEEK_HOURS - config.APPOINTMENT_LENGTH:
            raise ValueError("start must be a whole hour from 0 to 167")
        self.__id = int(id)
        self.__patient = patient
        self.__staff = staff
        self.__start = int(start)
        self.__status = Status.PENDING
        self.__reason = ""

    @property
    def id(self):
        return self.__id

    @property
    def patient(self):
        return self.__patient

    @property
    def staff(self):
        return self.__staff

    @property
    def start(self):
        return self.__start

    @property
    def end(self):
        return self.__start + config.APPOINTMENT_LENGTH

    @property
    def status(self):
        return self.__status

    @property
    def reason(self):
        return self.__reason

    @property
    def active(self):
        return self.__status is not Status.CANCELLED

    def view(self):
        return AppointmentView(
            self.__id,
            self.__patient.id,
            self.__staff.id,
            self.__start,
            self.__status,
            self.__reason,
        )

    def check_confirm(self, now):
        self.__need_legal(Status.CONFIRMED)
        self.__need_not_started(now)

    def check_cancel(self, now):
        self.__need_legal(Status.CANCELLED)
        self.__need_not_started(now)
        if self.__status is Status.CONFIRMED and self.__start - now < config.CANCEL_NOTICE_HOURS:
            raise RuleViolation("too late")

    def confirm(self, now):
        self.check_confirm(now)
        self.__status = Status.CONFIRMED

    def cancel(self, now, reason=""):
        self.check_cancel(now)
        self.__status = Status.CANCELLED
        self.__reason = str(reason)

    def __need_legal(self, target):
        if self.__status is Status.CANCELLED:
            raise IllegalTransition("already cancelled")
        if target not in _LEGAL[self.__status]:
            raise IllegalTransition(f"illegal transition {self.__status.name} -> {target.name}")

    def __need_not_started(self, now):
        if now >= self.__start:
            raise RuleViolation("already started")
