import sys
from contextlib import contextmanager

from .appointment import Appointment
from .errors import LogError, NotFound, RuleViolation
from .log import AppointmentLog


# Invariants of Clinic:
#  1. Person ids (patients and staff together) are unique positive integers.
#  2. Appointment ids are unique, assigned by the clinic from 1 upward and never reused.
#  3. Every appointment refers to a registered patient and a registered staff member.
#  4. No staff member and no patient has two non-cancelled appointments at the same hour.
#  5. A waiting list belongs to one registered staff member, holds registered patients,
#     lists each patient at most once and keeps join order.
#  6. Every change is written to the log before it is applied; a failed action
#     leaves the state unchanged and is logged as FAILED.
#  7. The log is opened once when the clinic is entered and closed once when it is left,
#     whatever happens in between.
class Clinic:
    def __init__(self, clock, log_path, out=print, opener=open):
        self.__clock = clock
        self.__log = AppointmentLog(log_path, out=out, opener=opener)
        self.__patients = {}
        self.__staff = {}
        self.__appointments = {}
        self.__waiting = {}
        self.__next_id = 1

    def __enter__(self):
        self.__log.open()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.__log.close()
        except LogError as problem:
            if exc_type is None:
                raise
            print(f"log close failed: {problem}", file=sys.stderr)
        return False

    @property
    def log(self):
        return self.__log

    def staff(self):
        return tuple(self.__staff.values())

    def patients(self):
        return tuple(self.__patients.values())

    def appointments(self):
        return tuple(a.view() for a in self.__appointments.values())

    def appointment(self, appointment_id):
        return self.__find(appointment_id).view()

    def waiting_list(self, staff_id):
        self.__staff_member(staff_id)
        return tuple(self.__waiting.get(staff_id, ()))

    def add_patient(self, patient):
        with self.__action(f"register patient {patient.name}"):
            self.__need_new_id(patient.id)
            self.__record(f"registered patient #{patient.id} {patient.name}")
            self.__patients[patient.id] = patient

    def add_staff(self, member):
        with self.__action(f"register {member.role().lower()} {member.name}"):
            self.__need_new_id(member.id)
            self.__record(f"registered {member.role().lower()} #{member.id} {member.name}")
            self.__staff[member.id] = member
            self.__waiting[member.id] = []

    def book(self, patient_id, staff_id, start):
        label = f"book patient {patient_id} with staff {staff_id} at hour {start}"
        with self.__action(label):
            patient = self.__patient(patient_id)
            member = self.__staff_member(staff_id)
            appointment = self.__draft(patient, member, start)
            self.__record(
                f"booked #{appointment.id} {patient.name} with {member.name} at hour {start} PENDING"
            )
            self.__store(appointment)
            return appointment.id

    def confirm(self, appointment_id):
        with self.__action(f"confirm #{appointment_id}"):
            appointment = self.__find(appointment_id)
            now = self.__clock.now()
            appointment.check_confirm(now)
            self.__record(f"confirmed #{appointment_id}")
            appointment.confirm(now)

    def cancel(self, appointment_id, reason=""):
        with self.__action(f"cancel #{appointment_id}"):
            appointment = self.__find(appointment_id)
            now = self.__clock.now()
            appointment.check_cancel(now)
            candidate = self.__first_waiting(appointment)
            lines = [f"cancelled #{appointment_id} ({reason or 'no reason'})"]
            offer = None
            if candidate is not None:
                offer = Appointment(
                    self.__next_id, candidate, appointment.staff, appointment.start
                )
                lines.append(
                    f"offered slot hour {offer.start} of {offer.staff.name} to waiting "
                    f"{candidate.name}: new #{offer.id} PENDING"
                )
            self.__record(*lines)
            appointment.cancel(now, reason)
            if offer is not None:
                self.__store(offer)
                self.__waiting[offer.staff.id].remove(candidate.id)

    def join_waiting_list(self, patient_id, staff_id):
        label = f"waiting list patient {patient_id} for staff {staff_id}"
        with self.__action(label):
            patient = self.__patient(patient_id)
            member = self.__staff_member(staff_id)
            if patient_id in self.__waiting[staff_id]:
                raise RuleViolation("already on the waiting list")
            self.__record(f"{patient.name} joined the waiting list of {member.name}")
            self.__waiting[staff_id].append(patient_id)

    @contextmanager
    def __action(self, label):
        try:
            yield
        except LogError:
            raise
        except Exception as exc:
            try:
                self.__record(f"FAILED {label}: {exc}")
            except LogError:
                pass
            raise

    def __record(self, *texts):
        now = self.__clock.now()
        self.__log.write(*(f"[t={now}] {text}" for text in texts))

    def __need_new_id(self, number):
        if number in self.__patients or number in self.__staff:
            raise RuleViolation(f"id {number} already in use")

    def __patient(self, patient_id):
        if patient_id not in self.__patients:
            raise NotFound(f"no patient with id {patient_id}")
        return self.__patients[patient_id]

    def __staff_member(self, staff_id):
        if staff_id not in self.__staff:
            raise NotFound(f"no staff member with id {staff_id}")
        return self.__staff[staff_id]

    def __find(self, appointment_id):
        if appointment_id not in self.__appointments:
            raise NotFound(f"no appointment #{appointment_id}")
        return self.__appointments[appointment_id]

    def __conflict(self, patient, member, start):
        for other in self.__appointments.values():
            if other.active and other.start == start:
                if other.staff.id == member.id:
                    return f"{member.name} is busy at hour {start}"
                if other.patient.id == patient.id:
                    return f"{patient.name} is busy at hour {start}"
        return None

    def __draft(self, patient, member, start):
        appointment = Appointment(self.__next_id, patient, member, start)
        if start < self.__clock.now():
            raise RuleViolation("start is in the past")
        problem = self.__conflict(patient, member, start)
        if problem is not None:
            raise RuleViolation(problem)
        return appointment

    def __store(self, appointment):
        self.__appointments[appointment.id] = appointment
        self.__next_id = appointment.id + 1

    def __first_waiting(self, cancelled):
        member = cancelled.staff
        for patient_id in self.__waiting[member.id]:
            patient = self.__patients[patient_id]
            if patient.id == cancelled.patient.id:
                continue
            others = [
                a for a in self.__appointments.values() if a is not cancelled
            ]
            busy = any(
                a.active
                and a.start == cancelled.start
                and (a.patient.id == patient.id or a.staff.id == member.id)
                for a in others
            )
            if not busy:
                return patient
        return None
