import asyncio

import pytest

from llama_index.core.workflow.context import Context
from llama_index.core.workflow.decorators import step
from llama_index.core.workflow.events import Event, StartEvent, StopEvent
from llama_index.core.workflow.workflow import Workflow
from llama_index.core.workflow.errors import WorkflowRuntimeError

from .conftest import OneTestEvent

TEXT = "Paul Graham is a British-American computer scientist, entrepreneur, vc, and writer."


class StreamingWorkflow(Workflow):
    @step
    async def chat(self, ctx: Context, ev: StartEvent) -> StopEvent:
        async def stream_messages():
            for word in TEXT.split():
                yield word

        async for w in stream_messages():
            ctx.write_event_to_stream(Event(msg=w))

        return StopEvent(result=None)


@pytest.mark.asyncio()
async def test_e2e():
    wf = StreamingWorkflow()
    r = asyncio.create_task(wf.run())

    async for ev in wf.stream_events():
        assert "msg" in ev

    await r


@pytest.mark.asyncio()
async def test_too_many_runs():
    wf = StreamingWorkflow()
    r = asyncio.gather(wf.run(), wf.run())
    with pytest.raises(
        WorkflowRuntimeError,
        match="This workflow has multiple concurrent runs in progress and cannot stream events",
    ):
        async for ev in wf.stream_events():
            pass
    await r


@pytest.mark.asyncio()
async def test_task_raised():
    class DummyWorkflow(Workflow):
        @step
        async def step(self, ctx: Context, ev: StartEvent) -> StopEvent:
            ctx.write_event_to_stream(OneTestEvent(test_param="foo"))
            raise ValueError("The step raised an error!")

    wf = DummyWorkflow()
    r = asyncio.create_task(wf.run())

    # Make sure we don't block indefinitely here because the step raised
    async for ev in wf.stream_events():
        assert ev.test_param == "foo"

    # Make sure the await actually caught the exception
    with pytest.raises(ValueError, match="The step raised an error!"):
        await r


@pytest.mark.asyncio()
async def test_multiple_streams():
    wf = StreamingWorkflow()
    r = asyncio.create_task(wf.run())

    # stream 1
    async for _ in wf.stream_events():
        pass
    await r

    # stream 2 -- should not raise an error
    r = asyncio.create_task(wf.run())
    async for _ in wf.stream_events():
        pass
    await r


@pytest.mark.asyncio()
async def test_multiple_streams_at_the_same_time():
    wf = StreamingWorkflow()

    stream_1 = wf.stream_run()

    expected_stream_1_iters = len(TEXT.split()) + 1

    # running multiple streams should work, since they are separated by context

    stream_1_iters = 0
    stream_2_iters = 0
    async for _ in stream_1:
        stream_1_iters += 1
        async for _ in wf.stream_run():
            stream_2_iters += 1

    assert stream_1_iters == expected_stream_1_iters
    assert stream_2_iters == stream_1_iters * stream_1_iters


@pytest.mark.asyncio()
async def test_resume_streams():
    class CounterWorkflow(Workflow):
        @step
        async def count(self, ctx: Context, ev: StartEvent) -> StopEvent:
            ctx.write_event_to_stream(Event(msg="hello!"))

            cur_count = await ctx.get("cur_count", default=0)
            await ctx.set("cur_count", cur_count + 1)
            return StopEvent(result="done")

    wf = CounterWorkflow()
    stream_1 = wf.stream_run()

    async for item in stream_1:
        pass

    stream_2 = wf.stream_run(ctx=item.ctx)
    async for item in stream_2:
        pass

    assert await item.ctx.get("cur_count") == 2
