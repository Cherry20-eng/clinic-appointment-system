from abc import ABC, abstractmethod

from . import config


def _clean_name(value):
    try:
        text = value.strip()
    except AttributeError:
        raise TypeError("name must be text") from None
    if not text:
        raise ValueError("name must not be empty")
    return text


def _clean_id(value):
    try:
        number = value.__index__()
    except AttributeError:
        raise TypeError("id must be an integer") from None
    if number <= 0:
        raise ValueError("id must be a positive integer")
    return number


class Person(ABC):
    __constructions = 0

    def __init__(self, name, id, **kwargs):
        super().__init__(**kwargs)
        self.__name = _clean_name(name)
        self.__id = _clean_id(id)
        Person.__constructions += 1

    @property
    def name(self):
        return self.__name

    @property
    def id(self):
        return self.__id

    @abstractmethod
    def role(self):
        ...

    @classmethod
    def constructions(cls):
        return Person.__constructions

    def __repr__(self):
        return f"{self.role()}(#{self.id} {self.name})"


class Patient(Person):
    def role(self):
        return "Patient"


class Staff(Person):
    @abstractmethod
    def fee(self):
        ...


class Doctor(Staff):
    def role(self):
        return "Doctor"

    def fee(self):
        return 40 + 5 * (config.P % 5)


class Nurse(Staff):
    def role(self):
        return "Nurse"

    def fee(self):
        return 10 + (config.P % 3)


class Pharmacist(Staff):
    def role(self):
        return "Pharmacist"

    def fee(self):
        return 5


class Lecturer(Person):
    def __init__(self, *args, module, **kwargs):
        super().__init__(*args, **kwargs)
        self.__module = _clean_name(module)

    @property
    def module(self):
        return self.__module

    def role(self):
        return "Lecturer"


class MedicalLecturer(Doctor, Lecturer):
    def role(self):
        return "Doctor and Lecturer"

    def fee(self):
        return super().fee()
