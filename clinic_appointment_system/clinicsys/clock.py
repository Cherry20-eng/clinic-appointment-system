from abc import ABC, abstractmethod

from . import config


class Clock(ABC):
    @abstractmethod
    def now(self):
        ...


class ManualClock(Clock):
    def __init__(self, start=0):
        self.__now = 0
        self.set(start)

    def now(self):
        return self.__now

    def set(self, hour):
        if hour != int(hour) or not 0 <= hour <= config.WEEK_HOURS:
            raise ValueError(f"hour must be a whole number from 0 to {config.WEEK_HOURS}")
        if hour < self.__now:
            raise ValueError("time cannot move backwards")
        self.__now = int(hour)

    def advance(self, hours):
        if hours != int(hours) or hours < 0:
            raise ValueError("hours must be a non-negative whole number")
        self.set(self.__now + int(hours))
