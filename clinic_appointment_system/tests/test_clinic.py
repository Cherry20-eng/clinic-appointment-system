import ast
import tempfile
import unittest
from pathlib import Path

from clinicsys import (
    Appointment,
    Clinic,
    ClinicError,
    Doctor,
    IllegalTransition,
    Lecturer,
    LogError,
    ManualClock,
    MedicalLecturer,
    Nurse,
    NotFound,
    Patient,
    Person,
    Pharmacist,
    RuleViolation,
    Staff,
    Status,
    config,
)

PACKAGE = Path(__file__).resolve().parent.parent / "clinicsys"


class FakeStream:
    def __init__(self, fail_write=False, fail_close=False):
        self.fail_write = fail_write
        self.fail_close = fail_close
        self.lines = []
        self.closed = 0

    def write(self, text):
        if self.fail_write:
            raise OSError("disk full")
        self.lines.append(text)

    def flush(self):
        pass

    def close(self):
        self.closed += 1
        if self.fail_close:
            raise OSError("close failed")


def make_clinic(stream=None, start=0):
    clock = ManualClock(start)
    sink = []
    opener = (lambda *a, **k: stream) if stream is not None else (lambda *a, **k: FakeStream())
    clinic = Clinic(clock, "unused.log", out=sink.append, opener=opener)
    return clinic, clock, sink


def populate(clinic):
    clinic.add_staff(Doctor("Dr A", 1))
    clinic.add_staff(Nurse("Nurse B", 2))
    clinic.add_patient(Patient("Pat C", 10))
    clinic.add_patient(Patient("Pat D", 11))
    clinic.add_patient(Patient("Pat E", 12))


class ConstructionTests(unittest.TestCase):
    def test_rejects_bad_names_and_ids(self):
        for name in ("", "   "):
            with self.assertRaises(ValueError):
                Patient(name, 1)
        with self.assertRaises(TypeError):
            Patient(None, 1)
        for bad in (0, -3):
            with self.assertRaises(ValueError):
                Patient("X", bad)
        with self.assertRaises(TypeError):
            Patient("X", "7")

    def test_person_is_abstract(self):
        with self.assertRaises(TypeError):
            Person("X", 1)
        with self.assertRaises(TypeError):
            Staff("X", 1)

    def test_fields_hidden(self):
        patient = Patient("X", 1)
        with self.assertRaises(AttributeError):
            patient.name = "Y"
        with self.assertRaises(AttributeError):
            patient.id = 2


class FeeTests(unittest.TestCase):
    def test_formulas(self):
        self.assertEqual(Doctor("D", 1).fee(), 40 + 5 * (config.P % 5))
        self.assertEqual(Nurse("N", 2).fee(), 10 + config.P % 3)
        self.assertEqual(Pharmacist("P", 3).fee(), 5)

    def test_new_staff_subclass_needs_no_other_edit(self):
        class Receptionist(Staff):
            def role(self):
                return "Receptionist"

            def fee(self):
                return 1

        clinic, _, _ = make_clinic()
        with clinic:
            clinic.add_staff(Doctor("D", 1))
            clinic.add_staff(Receptionist("R", 2))
            report = [(m.role(), m.fee()) for m in clinic.staff()]
        self.assertEqual(report[-1], ("Receptionist", 1))

    def test_no_type_checks_in_source(self):
        banned = {"isinstance", "issubclass", "type"}
        for path in PACKAGE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, banned, f"{path.name}: {node.func.id}")


class MultipleInheritanceTests(unittest.TestCase):
    def test_single_person(self):
        before = Person.constructions()
        lecturer = MedicalLecturer("Prof", 7, module="Anatomy")
        self.assertEqual(Person.constructions() - before, 1)
        self.assertEqual(lecturer.role(), "Doctor and Lecturer")
        self.assertEqual(lecturer.module, "Anatomy")
        self.assertEqual(lecturer.fee(), Doctor("Dr", 8).fee())
        self.assertIsInstance(lecturer, Doctor)
        self.assertIsInstance(lecturer, Lecturer)

    def test_lecturer_needs_module(self):
        with self.assertRaises(ValueError):
            Lecturer("L", 1, module=" ")


class AppointmentTests(unittest.TestCase):
    def setUp(self):
        self.appt = Appointment(1, Patient("P", 10), Doctor("D", 1), 20)

    def test_pending_to_confirmed_to_cancelled(self):
        self.appt.confirm(0)
        self.assertIs(self.appt.status, Status.CONFIRMED)
        self.appt.cancel(10, "x")
        self.assertIs(self.appt.status, Status.CANCELLED)
        self.assertEqual(self.appt.reason, "x")

    def test_cancelled_never_returns(self):
        self.appt.cancel(0)
        with self.assertRaises(IllegalTransition):
            self.appt.confirm(0)
        with self.assertRaises(IllegalTransition):
            self.appt.cancel(0)

    def test_confirmed_cannot_return_to_pending_or_reconfirm(self):
        self.appt.confirm(0)
        with self.assertRaises(IllegalTransition):
            self.appt.confirm(0)

    def test_two_hour_rule_only_for_confirmed(self):
        self.appt.confirm(0)
        with self.assertRaisesRegex(RuleViolation, "too late"):
            self.appt.cancel(19)
        self.appt.cancel(18)

    def test_pending_may_be_cancelled_late_but_not_after_start(self):
        pending = Appointment(2, Patient("P", 10), Doctor("D", 1), 20)
        pending.cancel(19)
        again = Appointment(3, Patient("P", 10), Doctor("D", 1), 20)
        with self.assertRaisesRegex(RuleViolation, "already started"):
            again.cancel(20)

    def test_nothing_changes_after_start(self):
        with self.assertRaises(RuleViolation):
            self.appt.confirm(20)

    def test_start_range(self):
        for bad in (-1, 168):
            with self.assertRaises(ValueError):
                Appointment(1, Patient("P", 10), Doctor("D", 1), bad)


class ClinicRuleTests(unittest.TestCase):
    def test_conflicts_and_unique_ids(self):
        clinic, _, _ = make_clinic()
        with clinic:
            populate(clinic)
            clinic.book(10, 1, 20)
            with self.assertRaises(RuleViolation):
                clinic.book(11, 1, 20)
            with self.assertRaises(RuleViolation):
                clinic.book(10, 2, 20)
            with self.assertRaises(RuleViolation):
                clinic.add_patient(Patient("Same id", 1))
            with self.assertRaises(RuleViolation):
                clinic.add_staff(Nurse("Same id", 10))
            self.assertEqual(len(clinic.appointments()), 1)

    def test_cancelled_slot_can_be_rebooked(self):
        clinic, _, _ = make_clinic()
        with clinic:
            populate(clinic)
            first = clinic.book(10, 1, 20)
            clinic.cancel(first)
            clinic.book(11, 1, 20)

    def test_past_and_unknown(self):
        clinic, _, _ = make_clinic(start=30)
        with clinic:
            populate(clinic)
            with self.assertRaises(RuleViolation):
                clinic.book(10, 1, 20)
            with self.assertRaises(NotFound):
                clinic.book(99, 1, 40)
            with self.assertRaises(NotFound):
                clinic.cancel(5)

    def test_views_do_not_expose_internals(self):
        clinic, _, _ = make_clinic()
        with clinic:
            populate(clinic)
            clinic.book(10, 1, 20)
            self.assertIsInstance(clinic.staff(), tuple)
            self.assertIsInstance(clinic.waiting_list(1), tuple)
            self.assertIsInstance(clinic.appointments(), tuple)


class WaitingListTests(unittest.TestCase):
    def test_first_without_conflict_gets_offer(self):
        clinic, _, _ = make_clinic()
        with clinic:
            populate(clinic)
            booked = clinic.book(10, 1, 20)
            clinic.book(11, 2, 20)
            clinic.join_waiting_list(11, 1)
            clinic.join_waiting_list(12, 1)
            clinic.cancel(booked, "x")
            self.assertEqual(clinic.waiting_list(1), (11,))
            offered = clinic.appointments()[-1]
            self.assertEqual((offered.patient_id, offered.start, offered.status), (12, 20, Status.PENDING))
            self.assertTrue(any("offered slot" in line for line in clinic.log.entries()))

    def test_no_offer_when_nobody_waits(self):
        clinic, _, _ = make_clinic()
        with clinic:
            populate(clinic)
            booked = clinic.book(10, 1, 20)
            clinic.cancel(booked)
            self.assertEqual(len(clinic.appointments()), 1)

    def test_duplicate_join_rejected(self):
        clinic, _, _ = make_clinic()
        with clinic:
            populate(clinic)
            clinic.join_waiting_list(10, 1)
            with self.assertRaises(RuleViolation):
                clinic.join_waiting_list(10, 1)


class LogTests(unittest.TestCase):
    def test_open_close_once_normal(self):
        stream = FakeStream()
        clinic, _, sink = make_clinic(stream)
        with clinic:
            populate(clinic)
        self.assertEqual((clinic.log.opens, clinic.log.closes), (1, 1))
        self.assertEqual(sink.count("[log] opened"), 1)
        self.assertEqual(sink.count("[log] closed"), 1)
        self.assertEqual(stream.closed, 1)

    def test_closed_even_when_error_escapes(self):
        stream = FakeStream()
        clinic, _, sink = make_clinic(stream)
        with self.assertRaises(RuntimeError):
            with clinic:
                populate(clinic)
                raise RuntimeError("boom")
        self.assertEqual(sink.count("[log] closed"), 1)
        self.assertEqual(stream.closed, 1)

    def test_failed_actions_logged(self):
        clinic, clock, _ = make_clinic()
        with clinic:
            populate(clinic)
            booked = clinic.book(10, 1, 20)
            clinic.confirm(booked)
            clock.set(19)
            with self.assertRaises(RuleViolation):
                clinic.cancel(booked)
            self.assertIn(f"[t=19] FAILED cancel #{booked}: too late", clinic.log.entries())

    def test_cannot_reopen(self):
        clinic, _, _ = make_clinic()
        with clinic:
            pass
        with self.assertRaises(LogError):
            clinic.log.open()
        self.assertFalse(clinic.log.close())

    def test_actions_need_open_log(self):
        clinic, _, _ = make_clinic()
        with self.assertRaises(LogError):
            clinic.add_patient(Patient("P", 1))

    def test_write_failure_leaves_state_unchanged(self):
        stream = FakeStream()
        clinic, _, _ = make_clinic(stream)
        with clinic:
            populate(clinic)
            stream.fail_write = True
            with self.assertRaises(LogError):
                clinic.book(10, 1, 20)
            stream.fail_write = False
            self.assertEqual(clinic.appointments(), ())
            self.assertEqual(clinic.book(10, 1, 20), 1)

    def test_close_failure_reported_once(self):
        stream = FakeStream(fail_close=True)
        clinic, _, _ = make_clinic(stream)
        with self.assertRaises(LogError):
            with clinic:
                populate(clinic)
        self.assertEqual(stream.closed, 1)
        self.assertEqual(clinic.log.closes, 1)

    def test_close_failure_does_not_mask_original_error(self):
        stream = FakeStream(fail_close=True)
        clinic, _, _ = make_clinic(stream)
        with self.assertRaises(RuntimeError):
            with clinic:
                raise RuntimeError("boom")


class ClockTests(unittest.TestCase):
    def test_bounds_and_direction(self):
        clock = ManualClock(5)
        clock.advance(3)
        self.assertEqual(clock.now(), 8)
        with self.assertRaises(ValueError):
            clock.set(2)
        with self.assertRaises(ValueError):
            clock.set(169)
        with self.assertRaises(ValueError):
            ManualClock(-1)


if __name__ == "__main__":
    unittest.main()
