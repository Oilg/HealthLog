class BaseError(Exception):
    message = "Unexpected exception"

    @property
    def code(self) -> str:
        return self.message.lower().replace(" ", "_")

    def __repr__(self) -> str:
        context = [f"{key}: {value!r}" for key, value in self.__dict__.items()]
        context_repr = "\n".join(context)

        return f"{self.message}\n{context_repr}"

    __str__ = __repr__

    def __init__(self) -> None:
        super().__init__(self.message)


class NotFoundError(BaseError):
    status_code = 404
    message = "Not Found"
