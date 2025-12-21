from pydantic import BaseModel
import abc
import contextlib


class ContainerEnvironment(BaseModel):
    name: str
    first_port: int


class UnknownContainersCountException(Exception):
    pass


class ContainersManager(contextlib.AbstractContextManager, abc.ABC):
    @abc.abstractmethod
    def crete_containers_set(self, env: ContainerEnvironment) -> "ContainersSet":
        pass


class ContainersSet(abc.ABC):
    @abc.abstractmethod
    def get_running_count(self) -> int:
        pass

    @abc.abstractmethod
    def reset(self, count: int | None) -> int:
        pass
