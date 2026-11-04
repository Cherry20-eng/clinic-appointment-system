from pathlib import Path

from clinicsys import (
    Clinic,
    ClinicError,
    Doctor,
    Lecturer,
    ManualClock,
    MedicalLecturer,
    Nurse,
    Patient,
    Person,
    Pharmacist,
)


def heading(text):
    print()
    print(f"=== {text} ===")


def attempt(description, action):
    try:
        result = action()
    except (ClinicError, ValueError, TypeError) as problem:
        print(f"  expected failure -> {description}: {problem}")
        return None
    print(f"  ok -> {description}")
    return result


def main():
    clock = ManualClock(0)
    log_path = Path(__file__).with_name("appointments.log")
    log_path.write_text("", encoding="utf-8")

    try:
        with Clinic(clock, log_path) as clinic:
            heading("1. Staff, roles and fees (one loop, no type checks)")
            clinic.add_staff(Doctor("Dr Moyo", 1))
            clinic.add_staff(Nurse("Nurse Dube", 2))
            clinic.add_staff(Pharmacist("Pharm Ncube", 3))
            clinic.add_staff(MedicalLecturer("Prof Sibanda", 4, module="Anatomy"))
            for member in clinic.staff():
                print(f"  {member.role():<20} fee {member.fee()}")

            heading("2. Patients and uniqueness of ids")
            for number, name in ((10, "Ana"), (11, "Ben"), (12, "Chipo")):
                clinic.add_patient(Patient(name, number))
            attempt("register a patient reusing id 1", lambda: clinic.add_patient(Patient("Dup", 1)))
            attempt("empty name rejected", lambda: Patient("   ", 99))
            attempt("non-positive id rejected", lambda: Patient("Zed", 0))

            heading("3. Booking, confirming, conflict rules")
            first = clinic.book(10, 1, 20)
            second = clinic.book(11, 1, 21)
            clinic.confirm(first)
            attempt("same staff, same hour", lambda: clinic.book(12, 1, 20))
            attempt("same patient, same hour", lambda: clinic.book(10, 2, 20))
            attempt("unknown staff", lambda: clinic.book(10, 77, 30))
            for view in clinic.appointments():
                print(f"  #{view.id} patient {view.patient_id} staff {view.staff_id} "
                      f"hour {view.start} {view.status.name}")

            heading("4. Waiting list (owned by the clinic)")
            clinic.join_waiting_list(12, 1)
            clinic.join_waiting_list(11, 1)
            attempt("joining twice", lambda: clinic.join_waiting_list(12, 1))
            print("  waiting for Dr Moyo:", clinic.waiting_list(1))
            clinic.cancel(second, "patient request")
            print("  waiting for Dr Moyo:", clinic.waiting_list(1))
            for view in clinic.appointments():
                print(f"  #{view.id} patient {view.patient_id} hour {view.start} "
                      f"{view.status.name} {view.reason}")
            attempt("cancelled appointment cannot return", lambda: clinic.confirm(second))
            attempt("cancel twice", lambda: clinic.cancel(second))

            heading("5. Multiple inheritance and a single Person")
            before = Person.constructions()
            lecturer = MedicalLecturer("Prof Khumalo", 5, module="Pharmacology")
            print(f"  role: {lecturer.role()}  module: {lecturer.module}  fee: {lecturer.fee()}")
            print(f"  Person constructor ran {Person.constructions() - before} time(s)")
            print(f"  is also a Lecturer: {lecturer.role().endswith('Lecturer')}, "
                  f"base class Lecturer fee not defined: {not hasattr(Lecturer, 'fee')}")

            heading("6. Clock-driven rules")
            clock.advance(19)
            print(f"  now = {clock.now()}; confirmed #{first} starts at 20")
            attempt("cancel confirmed appointment 1 hour before start", lambda: clinic.cancel(first))

            heading("7. Deliberate failure inside the clinic (log must still close)")
            clock.advance(1)
            clinic.cancel(first)
    except ClinicError as problem:
        print(f"demo stopped by the deliberate failure: {problem}")

    heading("Log file content")
    print(log_path.read_text(encoding="utf-8"), end="")


if __name__ == "__main__":
    main()
