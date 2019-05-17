# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest import mock

import pytest

from google.cloud.ndb import context as context_module
from google.cloud.ndb import _eventloop
from google.cloud.ndb import _remote
from google.cloud.ndb import tasklets

import tests.unit.utils


def test___all__():
    tests.unit.utils.verify___all__(tasklets)


def test_add_flow_exception():
    with pytest.raises(NotImplementedError):
        tasklets.add_flow_exception()


class TestFuture:
    @staticmethod
    def test_constructor():
        future = tasklets.Future()
        assert future.running()
        assert not future.done()
        assert future.info == "Unknown"

    @staticmethod
    def test_constructor_w_info():
        future = tasklets.Future("Testing")
        assert future.running()
        assert not future.done()
        assert future.info == "Testing"

    @staticmethod
    def test___repr__():
        future = tasklets.Future("The Children")
        assert repr(future) == "Future('The Children') <{}>".format(id(future))

    @staticmethod
    def test_set_result():
        future = tasklets.Future()
        future.set_result(42)
        assert future.result() == 42
        assert future.get_result() == 42
        assert future.done()
        assert not future.running()
        assert future.exception() is None
        assert future.get_exception() is None
        assert future.get_traceback() is None

    @staticmethod
    def test_set_result_already_done():
        future = tasklets.Future()
        future.set_result(42)
        with pytest.raises(RuntimeError):
            future.set_result(42)

    @staticmethod
    def test_add_done_callback():
        callback1 = mock.Mock()
        callback2 = mock.Mock()
        future = tasklets.Future()
        future.add_done_callback(callback1)
        future.add_done_callback(callback2)
        future.set_result(42)

        callback1.assert_called_once_with(future)
        callback2.assert_called_once_with(future)

    @staticmethod
    def test_add_done_callback_already_done():
        callback = mock.Mock()
        future = tasklets.Future()
        future.set_result(42)
        future.add_done_callback(callback)
        callback.assert_called_once_with(future)

    @staticmethod
    def test_set_exception():
        future = tasklets.Future()
        error = Exception("Spurious Error")
        future.set_exception(error)
        assert future.exception() is error
        assert future.get_exception() is error
        assert future.get_traceback() is error.__traceback__
        with pytest.raises(Exception):
            future.result()

    @staticmethod
    def test_set_exception_with_callback():
        callback = mock.Mock()
        future = tasklets.Future()
        future.add_done_callback(callback)
        error = Exception("Spurious Error")
        future.set_exception(error)
        assert future.exception() is error
        assert future.get_exception() is error
        assert future.get_traceback() is error.__traceback__
        callback.assert_called_once_with(future)

    @staticmethod
    def test_set_exception_already_done():
        future = tasklets.Future()
        error = Exception("Spurious Error")
        future.set_exception(error)
        with pytest.raises(RuntimeError):
            future.set_exception(error)

    @staticmethod
    @mock.patch("google.cloud.ndb.tasklets._eventloop")
    def test_wait(_eventloop):
        def side_effects(future):
            yield
            yield
            future.set_result(42)
            yield

        future = tasklets.Future()
        _eventloop.run1.side_effect = side_effects(future)
        future.wait()
        assert future.result() == 42
        assert _eventloop.run1.call_count == 3

    @staticmethod
    @mock.patch("google.cloud.ndb.tasklets._eventloop")
    def test_check_success(_eventloop):
        def side_effects(future):
            yield
            yield
            future.set_result(42)
            yield

        future = tasklets.Future()
        _eventloop.run1.side_effect = side_effects(future)
        future.check_success()
        assert future.result() == 42
        assert _eventloop.run1.call_count == 3

    @staticmethod
    @mock.patch("google.cloud.ndb.tasklets._eventloop")
    def test_check_success_failure(_eventloop):
        error = Exception("Spurious error")

        def side_effects(future):
            yield
            yield
            future.set_exception(error)
            yield

        future = tasklets.Future()
        _eventloop.run1.side_effect = side_effects(future)
        with pytest.raises(Exception) as error_context:
            future.check_success()

        assert error_context.value is error

    @staticmethod
    @mock.patch("google.cloud.ndb.tasklets._eventloop")
    def test_result_block_for_result(_eventloop):
        def side_effects(future):
            yield
            yield
            future.set_result(42)
            yield

        future = tasklets.Future()
        _eventloop.run1.side_effect = side_effects(future)
        assert future.result() == 42
        assert _eventloop.run1.call_count == 3

    @staticmethod
    def test_cancel():
        future = tasklets.Future()
        with pytest.raises(NotImplementedError):
            future.cancel()

    @staticmethod
    def test_cancelled():
        future = tasklets.Future()
        assert future.cancelled() is False

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_wait_any():
        futures = [tasklets.Future() for _ in range(3)]

        def callback():
            futures[1].set_result(42)

        _eventloop.add_idle(callback)

        future = tasklets.Future.wait_any(futures)
        assert future is futures[1]
        assert future.result() == 42

    @staticmethod
    def test_wait_any_no_futures():
        assert tasklets.Future.wait_any(()) is None

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_wait_all():
        futures = [tasklets.Future() for _ in range(3)]

        def make_callback(index, result):
            def callback():
                futures[index].set_result(result)

            return callback

        _eventloop.add_idle(make_callback(0, 42))
        _eventloop.add_idle(make_callback(1, 43))
        _eventloop.add_idle(make_callback(2, 44))

        tasklets.Future.wait_all(futures)
        assert futures[0].done()
        assert futures[0].result() == 42
        assert futures[1].done()
        assert futures[1].result() == 43
        assert futures[2].done()
        assert futures[2].result() == 44

    @staticmethod
    def test_wait_all_no_futures():
        assert tasklets.Future.wait_all(()) is None


class Test_TaskletFuture:
    @staticmethod
    def test_constructor():
        generator = object()
        context = object()
        future = tasklets._TaskletFuture(generator, context)
        assert future.generator is generator
        assert future.context is context
        assert future.info == "Unknown"

    @staticmethod
    def test___repr__():
        future = tasklets._TaskletFuture(None, None, info="Female")
        assert repr(future) == "_TaskletFuture('Female') <{}>".format(
            id(future)
        )

    @staticmethod
    def test__advance_tasklet_return(in_context):
        def generator_function():
            yield
            return 42

        generator = generator_function()
        next(generator)  # skip ahead to return
        future = tasklets._TaskletFuture(generator, in_context)
        future._advance_tasklet()
        assert future.result() == 42

    @staticmethod
    def test__advance_tasklet_generator_raises(in_context):
        error = Exception("Spurious error.")

        def generator_function():
            yield
            raise error

        generator = generator_function()
        next(generator)  # skip ahead to return
        future = tasklets._TaskletFuture(generator, in_context)
        future._advance_tasklet()
        assert future.exception() is error

    @staticmethod
    def test__advance_tasklet_bad_yield(in_context):
        def generator_function():
            yield 42

        generator = generator_function()
        future = tasklets._TaskletFuture(generator, in_context)
        with pytest.raises(RuntimeError):
            future._advance_tasklet()

    @staticmethod
    def test__advance_tasklet_dependency_returns(in_context):
        def generator_function(dependency):
            some_value = yield dependency
            return some_value + 42

        dependency = tasklets.Future()
        generator = generator_function(dependency)
        future = tasklets._TaskletFuture(generator, in_context)
        future._advance_tasklet()
        dependency.set_result(21)
        assert future.result() == 63

    @staticmethod
    def test__advance_tasklet_dependency_raises(in_context):
        def generator_function(dependency):
            yield dependency

        error = Exception("Spurious error.")
        dependency = tasklets.Future()
        generator = generator_function(dependency)
        future = tasklets._TaskletFuture(generator, in_context)
        future._advance_tasklet()
        dependency.set_exception(error)
        assert future.exception() is error
        with pytest.raises(Exception):
            future.result()

    @staticmethod
    def test__advance_tasklet_yields_rpc(in_context):
        def generator_function(dependency):
            value = yield dependency
            return value + 3

        dependency = mock.Mock(spec=_remote.RemoteCall)
        dependency.exception.return_value = None
        dependency.result.return_value = 8
        generator = generator_function(dependency)
        future = tasklets._TaskletFuture(generator, in_context)
        future._advance_tasklet()

        callback = dependency.add_done_callback.call_args[0][0]
        callback(dependency)
        _eventloop.run()
        assert future.result() == 11

    @staticmethod
    def test__advance_tasklet_parallel_yield(in_context):
        def generator_function(dependencies):
            one, two = yield dependencies
            return one + two

        dependencies = (tasklets.Future(), tasklets.Future())
        generator = generator_function(dependencies)
        future = tasklets._TaskletFuture(generator, in_context)
        future._advance_tasklet()
        dependencies[0].set_result(8)
        dependencies[1].set_result(3)
        assert future.result() == 11
        assert future.context is in_context


class Test_MultiFuture:
    @staticmethod
    def test___repr__():
        this, that = (tasklets.Future("this"), tasklets.Future("that"))
        future = tasklets._MultiFuture((this, that))
        assert repr(future) == (
            "_MultiFuture(Future('this') <{}>,"
            " Future('that') <{}>) <{}>".format(id(this), id(that), id(future))
        )

    @staticmethod
    def test_success():
        dependencies = (tasklets.Future(), tasklets.Future())
        future = tasklets._MultiFuture(dependencies)
        dependencies[0].set_result("one")
        dependencies[1].set_result("two")
        assert future.result() == ("one", "two")

    @staticmethod
    def test_error():
        dependencies = (tasklets.Future(), tasklets.Future())
        future = tasklets._MultiFuture(dependencies)
        error = Exception("Spurious error.")
        dependencies[0].set_exception(error)
        dependencies[1].set_result("two")
        assert future.exception() is error
        with pytest.raises(Exception):
            future.result()


class Test__get_return_value:
    @staticmethod
    def test_no_args():
        stop = StopIteration()
        assert tasklets._get_return_value(stop) is None

    @staticmethod
    def test_one_arg():
        stop = StopIteration(42)
        assert tasklets._get_return_value(stop) == 42

    @staticmethod
    def test_two_args():
        stop = StopIteration(42, 21)
        assert tasklets._get_return_value(stop) == (42, 21)


class Test_tasklet:
    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_generator():
        @tasklets.tasklet
        def generator(dependency):
            value = yield dependency
            return value + 3

        dependency = tasklets.Future()
        future = generator(dependency)
        assert isinstance(future, tasklets._TaskletFuture)
        dependency.set_result(8)
        assert future.result() == 11

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_regular_function():
        @tasklets.tasklet
        def regular_function(value):
            return value + 3

        future = regular_function(8)
        assert isinstance(future, tasklets.Future)
        assert future.result() == 11

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_regular_function_raises_Return():
        @tasklets.tasklet
        def regular_function(value):
            raise tasklets.Return(value + 3)

        future = regular_function(8)
        assert isinstance(future, tasklets.Future)
        assert future.result() == 11

    @staticmethod
    def test_context_management(in_context):
        @tasklets.tasklet
        def some_task(transaction, future):
            assert context_module.get_context().transaction == transaction
            yield future
            return context_module.get_context().transaction

        future_foo = tasklets.Future("foo")
        with in_context.new(transaction="foo").use():
            task_foo = some_task("foo", future_foo)

        future_bar = tasklets.Future("bar")
        with in_context.new(transaction="bar").use():
            task_bar = some_task("bar", future_bar)

        future_foo.set_result(None)
        future_bar.set_result(None)

        assert task_foo.result() == "foo"
        assert task_bar.result() == "bar"

    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_context_changed_in_tasklet():
        @tasklets.tasklet
        def some_task(transaction, future1, future2):
            context = context_module.get_context()
            assert context.transaction is None
            with context.new(transaction=transaction).use():
                assert context_module.get_context().transaction == transaction
                yield future1
                assert context_module.get_context().transaction == transaction
                yield future2
                assert context_module.get_context().transaction == transaction
            assert context_module.get_context() is context

        future_foo1 = tasklets.Future("foo1")
        future_foo2 = tasklets.Future("foo2")
        task_foo = some_task("foo", future_foo1, future_foo2)

        future_bar1 = tasklets.Future("bar1")
        future_bar2 = tasklets.Future("bar2")
        task_bar = some_task("bar", future_bar1, future_bar2)

        future_foo1.set_result(None)
        future_bar1.set_result(None)
        future_foo2.set_result(None)
        future_bar2.set_result(None)

        task_foo.check_success()
        task_bar.check_success()


class Test_wait_any:
    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_it():
        futures = [tasklets.Future() for _ in range(3)]

        def callback():
            futures[1].set_result(42)

        _eventloop.add_idle(callback)

        future = tasklets.wait_any(futures)
        assert future is futures[1]
        assert future.result() == 42

    @staticmethod
    def test_it_no_futures():
        assert tasklets.wait_any(()) is None


class Test_wait_all:
    @staticmethod
    @pytest.mark.usefixtures("in_context")
    def test_it():
        futures = [tasklets.Future() for _ in range(3)]

        def make_callback(index, result):
            def callback():
                futures[index].set_result(result)

            return callback

        _eventloop.add_idle(make_callback(0, 42))
        _eventloop.add_idle(make_callback(1, 43))
        _eventloop.add_idle(make_callback(2, 44))

        tasklets.wait_all(futures)
        assert futures[0].done()
        assert futures[0].result() == 42
        assert futures[1].done()
        assert futures[1].result() == 43
        assert futures[2].done()
        assert futures[2].result() == 44

    @staticmethod
    def test_it_no_futures():
        assert tasklets.wait_all(()) is None


@pytest.mark.usefixtures("in_context")
@mock.patch("google.cloud.ndb._eventloop.time")
def test_sleep(time_module, context):
    time_module.time.side_effect = [0, 0, 1]
    future = tasklets.sleep(1)
    assert future.get_result() is None
    time_module.sleep.assert_called_once_with(1)


def test_make_context():
    with pytest.raises(NotImplementedError):
        tasklets.make_context()


def test_make_default_context():
    with pytest.raises(NotImplementedError):
        tasklets.make_default_context()


class TestQueueFuture:
    @staticmethod
    def test_constructor():
        with pytest.raises(NotImplementedError):
            tasklets.QueueFuture()


class TestReducingFuture:
    @staticmethod
    def test_constructor():
        with pytest.raises(NotImplementedError):
            tasklets.ReducingFuture()


def test_Return():
    assert issubclass(tasklets.Return, StopIteration)


class TestSerialQueueFuture:
    @staticmethod
    def test_constructor():
        with pytest.raises(NotImplementedError):
            tasklets.SerialQueueFuture()


def test_set_context():
    with pytest.raises(NotImplementedError):
        tasklets.set_context()


@pytest.mark.usefixtures("in_context")
def test_synctasklet():
    @tasklets.synctasklet
    def generator_function(value):
        future = tasklets.Future(value)
        future.set_result(value)
        x = yield future
        return x + 3

    result = generator_function(8)
    assert result == 11


def test_toplevel():
    with pytest.raises(NotImplementedError):
        tasklets.toplevel()
