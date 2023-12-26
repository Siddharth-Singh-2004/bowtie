"""
Hand crafted classes which should undoubtedly be autogenerated from the schema.
"""
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, TypeVar, cast
import re

try:
    from typing import dataclass_transform
except ImportError:
    from typing_extensions import dataclass_transform

import json

from attrs import asdict, field, frozen
from referencing import Registry, Specification
from referencing.jsonschema import Schema, SchemaRegistry, specification_with

from bowtie import HOMEPAGE, exceptions

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Mapping

    from url import URL

    from bowtie._core import DialectRunner
    from bowtie._report import CaseReporter


Seq = int


@frozen
class Test:
    description: str
    instance: Any
    comment: str | None = None
    valid: bool | None = None


@frozen
class TestCase:
    description: str
    schema: Any
    tests: list[Test]
    comment: str | None = None
    registry: SchemaRegistry = Registry()

    @classmethod
    def from_dict(
        cls,
        dialect: URL,
        tests: Iterable[dict[str, Any]],
        registry: Mapping[str, Schema] = {},
        **kwargs: Any,
    ) -> TestCase:
        populated: SchemaRegistry = Registry().with_contents(  # type: ignore[reportUnknownMemberType]
            registry.items(),
            default_specification=specification_with(
                str(dialect),
                default=Specification.OPAQUE,
            ),
        )
        return cls(
            tests=[Test(**test) for test in tests],
            registry=populated,
            **kwargs,
        )

    def run(
        self,
        seq: Seq,
        runner: DialectRunner,
    ) -> Awaitable[ReportableResult]:
        command = Run(seq=seq, case=self.without_expected_results())
        return runner.run_validation(command=command, tests=self.tests)

    def serializable(self) -> dict[str, Any]:
        as_dict = asdict(
            self,
            filter=lambda k, v: k.name != "registry"
            and (k.name != "comment" or v is not None),
        )
        if self.registry:
            # FIXME: Via python-jsonschema/referencing#16
            as_dict["registry"] = {
                k: v.contents for k, v in self.registry.items()
            }
        return as_dict

    def without_expected_results(self) -> dict[str, Any]:
        serializable = self.serializable()
        serializable["tests"] = [
            {
                k: v
                for k, v in test.items()
                if k != "valid" and (k != "comment" or v is not None)
            }
            for test in serializable.pop("tests")
        ]
        return serializable


@frozen
class Started:
    implementation: dict[str, Any]
    ready: bool = field()
    version: int = field(
        validator=lambda _, __, got: exceptions.VersionMismatch.check(got),
    )

    @ready.validator  # type: ignore[reportGeneralTypeIssues]
    def _check_ready(self, _: Any, ready: bool):
        if not ready:
            raise exceptions.ImplementationNotReady()


R_co = TypeVar("R_co", covariant=True)


class Command(Protocol[R_co]):
    def to_request(self, validate: Callable[..., None]) -> dict[str, Any]:
        ...

    @staticmethod
    def from_response(
        response: bytes,
        validate: Callable[..., None],
    ) -> R_co | None:
        ...


@dataclass_transform()
def command(
    Response: Callable[..., R_co | None],
    name: str = "",
) -> Callable[[type], type[Command[R_co]]]:
    def _command(cls: type) -> type[Command[R_co]]:
        nonlocal name
        if not name:
            name = re.sub(r"([a-z])([A-Z])", r"\1-\2", cls.__name__).lower()

        uri = f"tag:{HOMEPAGE.host_str},2023:ihop:command:{name}"
        request_schema = {"$ref": str(uri)}
        response_schema = {"$ref": f"{uri}#response"}  # FIXME: crate-py/url#6

        def to_request(
            self: Command[R_co],
            validate: Callable[..., None],
        ) -> dict[str, Any]:
            request = dict(cmd=name, **asdict(self))
            validate(instance=request, schema=request_schema)
            return request

        @staticmethod
        def from_response(
            response: bytes,
            validate: Callable[..., None],
        ) -> R_co | None:
            try:
                instance = json.loads(response)
            except json.JSONDecodeError as error:
                raise exceptions._ProtocolError(errors=[error]) from error  # type: ignore[reportPrivateUsage]
            validate(instance=instance, schema=response_schema)
            return Response(**instance)

        cls = cast(type[Command[R_co]], cls)
        cls.to_request = to_request
        cls.from_response = from_response
        return frozen(cls)

    return _command


@command(Response=Started)
class Start:
    version: int


START_V1 = Start(version=1)


@frozen
class StartedDialect:
    ok: bool

    OK: ClassVar[StartedDialect]


StartedDialect.OK = StartedDialect(ok=True)


@command(Response=StartedDialect)
class Dialect:
    dialect: str


def _case_result(
    errored: bool = False,
    skipped: bool = False,
    **response: Any,
) -> Callable[[str, bool | None], AnyCaseResult]:
    if errored:
        return lambda implementation, expected: CaseErrored(
            implementation=implementation,
            **response,
        )
    elif skipped:
        return lambda implementation, expected: CaseSkipped(
            implementation=implementation,
            **response,
        )
    return lambda implementation, expected: CaseResult.from_dict(
        response,
        implementation=implementation,
        expected=expected,
    )


class AnyTestResult(Protocol):
    @property
    def description(self) -> str:
        """
        A single word to use when displaying this result.
        """
        ...

    @property
    def skipped(self) -> bool:
        ...

    @property
    def errored(self) -> bool:
        ...


@frozen
class TestResult:
    errored = False
    skipped = False

    valid: bool

    @property
    def description(self):
        return "valid" if self.valid else "invalid"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnyTestResult:
        if data.pop("skipped", False):
            return SkippedTest(**data)
        elif data.pop("errored", False):
            return ErroredTest(**data)
        return cls(valid=data["valid"])


TestResult.VALID = TestResult(valid=True)  # type: ignore[reportGeneralTypeIssues]
TestResult.INVALID = TestResult(valid=False)  # type: ignore[reportGeneralTypeIssues]


@frozen
class SkippedTest:
    message: str | None = field(default=None)
    issue_url: str | None = field(default=None)

    errored = False
    skipped: bool = field(init=False, default=True)

    description = "skipped"

    @property
    def reason(self) -> str:
        if self.message is not None:
            return self.message
        if self.issue_url is not None:
            return self.issue_url
        return "skipped"

    @classmethod
    def in_skipped_case(cls):
        """
        A skipped test which mentions it is part of an entirely skipped case.
        """
        return cls(message="All tests in this test case were skipped.")


@frozen
class ErroredTest:
    context: dict[str, Any] = field(factory=dict)

    errored: bool = field(init=False, default=True)
    skipped: bool = False

    description = "error"

    @property
    def reason(self) -> str:
        message = self.context.get("message")
        if message:
            return message
        return "Encountered an error."

    @classmethod
    def in_errored_case(cls):
        """
        A errored test which mentions it is part of an entirely errored case.
        """
        return cls(
            context=dict(message="All tests in this test case errored."),
        )


class ReportableResult(Protocol):
    errored: bool
    failed: bool

    @property
    def implementation(self) -> str:
        ...

    def report(self, reporter: CaseReporter) -> None:
        pass


@frozen
class CaseResult:
    errored = skipped = False

    implementation: str
    seq: Seq
    results: list[AnyTestResult]
    expected: list[bool | None]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], **kwargs: Any) -> CaseResult:
        results = [TestResult.from_dict(t) for t in data["results"]]
        return cls(
            results=results,
            **{k: v for k, v in data.items() if k != "results"},
            **kwargs,
        )

    @property
    def failed(self) -> bool:
        return any(failed for _, failed in self.compare())

    def report(self, reporter: CaseReporter) -> None:
        reporter.got_results(self)

    def compare(self) -> Iterable[tuple[AnyTestResult, bool]]:
        for test, expected in zip(self.results, self.expected):
            failed: bool = (  # type: ignore[reportUnknownVariableType]
                not test.skipped
                and not test.errored
                and expected is not None
                and expected != test.valid  # type: ignore[reportUnknownMemberType]
            )
            yield test, failed


@frozen
class CaseErrored:
    """
    A full test case errored.
    """

    errored = True
    failed = skipped = False

    implementation: str
    seq: Seq
    context: dict[str, Any]

    caught: bool = True

    @property
    def results(self) -> Mapping[Seq, AnyTestResult]:
        return defaultdict(ErroredTest.in_errored_case)

    def report(self, reporter: CaseReporter):
        reporter.case_errored(self)

    @classmethod
    def uncaught(
        cls,
        implementation: str,
        seq: Seq,
        **context: Any,
    ) -> CaseErrored:
        return cls(
            implementation=implementation,
            seq=seq,
            caught=False,
            context=context,
        )


@frozen
class CaseSkipped:
    """
    A full test case was skipped.
    """

    errored = failed = False

    implementation: str
    seq: Seq

    message: str | None = None
    issue_url: str | None = None
    skipped: bool = field(init=False, default=True)

    @property
    def results(self) -> Mapping[Seq, AnyTestResult]:
        return defaultdict(SkippedTest.in_skipped_case)

    def report(self, reporter: CaseReporter):
        reporter.skipped(self)


AnyCaseResult = CaseResult | CaseSkipped | CaseErrored


@frozen
class Empty:
    """
    An implementation didn't send a response.
    """

    errored = True
    failed = False

    implementation: str

    def report(self, reporter: CaseReporter):
        reporter.no_response(implementation=self.implementation)


@command(Response=_case_result)
class Run:
    seq: Seq
    case: dict[str, Any]


@command(Response=lambda: None)
class Stop:
    pass


STOP = Stop()
