from .errors import LogError


class AppointmentLog:
    def __init__(self, path, out=print, opener=open):
        self.__path = path
        self.__out = out
        self.__opener = opener
        self.__stream = None
        self.__state = "new"
        self.__entries = []
        self.__opens = 0
        self.__closes = 0

    @property
    def is_open(self):
        return self.__state == "open"

    @property
    def opens(self):
        return self.__opens

    @property
    def closes(self):
        return self.__closes

    def entries(self):
        return tuple(self.__entries)

    def open(self):
        if self.__state != "new":
            raise LogError("log can only be opened once")
        try:
            self.__stream = self.__opener(self.__path, "a", encoding="utf-8")
        except OSError as exc:
            raise LogError(f"cannot open log: {exc}") from exc
        self.__state = "open"
        self.__opens += 1
        self.__out("[log] opened")

    def write(self, *lines):
        if self.__state != "open":
            raise LogError("log is not open")
        try:
            for line in lines:
                self.__stream.write(line + "\n")
            self.__stream.flush()
        except OSError as exc:
            raise LogError(f"cannot write log: {exc}") from exc
        for line in lines:
            self.__entries.append(line)
            self.__out(f"  | {line}")

    def close(self):
        if self.__state != "open":
            return False
        stream = self.__stream
        self.__stream = None
        self.__state = "closed"
        self.__closes += 1
        try:
            stream.close()
        except OSError as exc:
            raise LogError(f"cannot close log: {exc}") from exc
        self.__out("[log] closed")
        return True
