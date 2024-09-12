import pytest

from llama_index.core.workflow.decorators import step
from llama_index.core.workflow.events import Event, StartEvent, StopEvent
from llama_index.core.workflow.workflow import Workflow
from llama_index.core.workflow.context import Context
from llama_index.core.workflow.service import ServiceManager, ServiceNotFoundError


class ServiceWorkflow(Workflow):
    """This wokflow is only responsible to generate a number, it knows nothing about the caller."""

    def __init__(self, *args, **kwargs) -> None:
        self._the_answer = kwargs.pop("the_answer", 42)
        super().__init__(*args, **kwargs)

    @step
    async def generate(self, ev: StartEvent) -> StopEvent:
        return StopEvent(result=self._the_answer)


class NumGenerated(Event):
    """To be used in the dummy workflow below."""

    num: int


class DummyWorkflow(Workflow):
    """
    This workflow needs a number, and it calls another workflow to get one.
    A service named "service_workflow" must be added to `DummyWorkflow` for
    the step to be able to use it (see below).
    This step knows nothing about the other workflow, it gets an instance
    and it only knows it has to call `run` on that instance.
    """

    @step
    async def get_a_number(
        self,
        ev: StartEvent,
        ctx: Context,
        service_workflow: ServiceWorkflow = ServiceWorkflow(),
    ) -> NumGenerated:
        workflow_result = await service_workflow.run()
        return NumGenerated(num=int(workflow_result.result))

    @step
    async def multiply(self, ev: NumGenerated) -> StopEvent:
        return StopEvent(ev.num * 2)


@pytest.mark.asyncio()
async def test_e2e():
    wf = DummyWorkflow()
    # We are responsible for passing the ServiceWorkflow instances to the dummy workflow
    # and give it a name, in this case "service_workflow"
    wf.add_workflows(service_workflow=ServiceWorkflow(the_answer=1337))
    workflow_result = await wf.run()
    assert workflow_result.result == 2674


@pytest.mark.asyncio()
async def test_default_value_for_service():
    wf = DummyWorkflow()
    # We don't add any workflow to leverage the default value defined by the user
    workflow_result = await wf.run()
    assert workflow_result.result == 84


def test_service_manager_add():
    s = ServiceManager()
    w = Workflow()
    s.add("test_id", w)
    assert s._services["test_id"] == w


def test_service_manager_get():
    s = ServiceManager()
    w = Workflow()
    s._services["test_id"] = w
    assert s.get("test_id") == w
    with pytest.raises(ServiceNotFoundError):
        s.get("not_found")
