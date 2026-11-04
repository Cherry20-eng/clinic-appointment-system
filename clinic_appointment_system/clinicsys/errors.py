class ClinicError(Exception):
    pass


class RuleViolation(ClinicError):
    pass


class IllegalTransition(RuleViolation):
    pass


class NotFound(ClinicError):
    pass


class LogError(ClinicError):
    pass
