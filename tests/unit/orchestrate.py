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

import itertools
import math
import queue
import threading


def orchestrate(*tests):
    """
    Orchestrate a deterministic concurrency test.

    Runs test functions in separate threads, with each thread taking turns running up
    until predefined syncpoints in a deterministic order. All possible orderings are
    tested.

    Most of the time, we try to use logic, best practices, and static analysis to insure
    correct operation of concurrent code. Sometimes our powers of reasoning fail us and,
    either through non-determistic stress testing or running code in production, a
    concurrent bug is discovered. When this occurs, we'd like to have a regression test
    to insure we've understood the problem and implemented a correct solution.
    `orchestrate` provides a means of deterministically testing concurrent code so we
    can write robust regression tests for complex concurrent scenarios.

    `orchestrate` runs each passed in test function in its own thread. Threads then
    "take turns" running. Turns are defined by setting syncpoints in the code under
    test. To do this, you'll write a no-op function and call it at the point where you'd
    like your code to pause and give another thread a turn. In your test, then, use
    `mock.patch` to replace your no-op function with :func:`syncpoint` in your test.

    For example, let's say you have the following code in production::

        def hither_and_yon(destination):
            hither(destination)
            yon(destination)

    You've found there's a concurrency bug when two threads execute this code with the
    same destination, and you think that by adding a syncpoint between the calls to
    `hither` and `yon` you can reproduce the problem in a regression test. First you'd,
    write a no-op function, include it in your production code, and call it in
    `hither_and_yon`::

        def _syncpoint_123():
            pass

        def hither_and_yon(destination):
            hither(destination)
            _syncpoint_123()
            yon(destination)

    Now you can write a test to exercise `hither_and_yon` running in parallel::

        from unittest import mock
        from tests.unit import orchestrate

        from google.cloud.sales import travel

        @mock.patch("google.cloud.sales.travel._syncpoint_123", orchestrate.syncpoint)
        def test_concurrent_hither_and_yon():

            def test_hither_and_yon():
                assert something
                travel.hither_and_yon("Raleigh")
                assert something_else

            counts = orchestrate.orchestrate(test_hither_and_yon, test_hither_and_yon)
            assert counts == (2, 2)

    What `orchestrate` will do now is take each of the two test functions passed in
    (actually the same function, twice, in this case), run them serially, and count the
    number of turns it takes to run each test to completion. In this example, it will
    take two turns for each test: one turn to start the thread and execute up until the
    syncpoint, and then another turn to execute from the syncpoint to the end of the
    test. The number of turns will always be one greater than the number of syncpoints
    encountered when executing the test.

    Once the counts have been taken, `orchestrate` will construct a test sequence that
    represents the all the turns taken by the passed in tests, with each value in the
    sequence representing the the index of the test whose turn it is in the sequence. In
    this example, then, it would produce::

        [0, 0, 1, 1]

    This represents the first test taking both of its turns, followed by the second test
    taking both of its turns. At this point this scenario has already been tested,
    because this is what was run to produce the counts and the initial test sequence.
    Now `orchestrate` will run all of the remaining scenarios by finding all the
    permutations of the test sequence and executing those, in turn::

        [0, 1, 0, 1]
        [0, 1, 1, 0]
        [1, 0, 0, 1]
        [1, 0, 1, 0]
        [1, 1, 0, 0]

    You'll notice in our example that since both test functions are actually the same
    function, that although it tested 6 scenarios there are effectively only really 3
    unique scenarios. For the time being, though, `orchestrate` doesn't attempt to
    detect this condition or optimize for it.

    There are some performance considerations that should be taken into account when
    writing tests. The number of unique test sequences grows quite quickly with the
    number of turns taken by the functions under test. Our simple example with two
    threads each taking two turns, only yielded 6 scenarios, but two threads each taking
    6 turns, for example, yields 924 scenarios. Add another six step thread and now you
    have over 17 thousand scenarios. In general, use the least number of steps/threads
    you can get away with and still expose the behavior you want to correct.

    For the same reason as above, if you have many concurrent tests, when writing a new
    test, make sure you're not accidentally patching syncpoints intended for other
    tests, as this will add steps to your tests. While it's not problematic from a
    testing standpoint to have extra steps in your tests, it can use computing resources
    unnecessarily. Using different no-op functions with different names for different
    tests can help with this.

    As soon as any error or failure is detected, no more scenarios are run
    and that error is propagated to the main thread.

    Args:
        tests (Tuple[Callable]): Test functions to be run. These functions will not be
            called with any arguments, so they must not have any required arguments.

    Returns:
        Tuple[int]: A tuple of the count of the number turns for test passed in. Can be
            used a sanity check in tests to make sure you understand what's actually
            happening during a test.
    """
    # Produce an initial test sequence. The fundamental question we're always trying to
    # answer is "whose turn is it?" First we'll find out how many "turns" each test
    # needs to complete when run serially and use that to construct a sequence of
    # indexes. When a test's index appears in the sequence, it is that test's turn to
    # run. We'll start by constructing a sequence that would run each test through to
    # completion serially, one after the other.
    test_sequence = []
    counts = []
    for index, test in enumerate(tests):
        thread = _TestThread(test)
        for count in itertools.count(1):  # pragma: NO BRANCH
            # Pragma is required because loop never finishes naturally.
            thread.go()
            if thread.finished:
                break

        counts.append(count)
        test_sequence += [index] * count

    # Now we can take that initial sequence and generate all of its permutations,
    # running each one to try to uncover concurrency bugs
    sequences = iter(_permutations(test_sequence))

    # We already tested the first sequence getting our counts, so we can discard it
    next(sequences)

    # Test each sequence
    for test_sequence in sequences:
        threads = [_TestThread(test) for test in tests]
        try:
            for index in test_sequence:
                threads[index].go()

            # Its possible for number of turns to vary from one test run to the other,
            # especially if there is some undiscovered concurrency bug. Go ahead and
            # finish running each test to completion, if not already complete.
            for thread in threads:
                while not thread.finished:
                    thread.go()

        except Exception:
            # If an exception occurs, we still need to let any threads that are still
            # going finish up. Additional exceptions are silently ignored.
            for thread in threads:
                thread.finish()
            raise

    return tuple(counts)


def syncpoint():
    """End a thread's "turn" at this point.

    This will generally be inserted by `mock.patch` to replace a no-op function in
    production code. See documentation for :func:`orchestrate`.
    """
    conductor = _local.conductor
    conductor.notify()
    conductor.standby()


_local = threading.local()


class _Conductor:
    """Coordinate communication between main thread and a test thread.

    Two way communicaton is maintained between the main thread and a test thread using
    two synchronized queues (`queue.Queue`) each with a size of one.
    """

    def __init__(self):
        self._notify = queue.Queue(1)
        self._go = queue.Queue(1)

    def notify(self):
        """Called from test thread to let us know it's finished or is ready for its next
        turn."""
        self._notify.put(None)

    def standby(self):
        """Called from test thread in order to block until told to go."""
        self._go.get()

    def wait(self):
        """Called from main thread to wait for test thread to either get to the
        next syncpoint or finish."""
        self._notify.get()

    def go(self):
        """Called from main thread to tell test thread to go."""
        self._go.put(None)


class _TestThread:
    """A thread for a test function."""

    thread = None
    finished = False
    error = None

    def __init__(self, test):
        self.test = test
        self.conductor = _Conductor()

    def _run(self):
        _local.conductor = self.conductor
        try:
            self.test()
        except Exception as error:
            self.error = error
        finally:
            self.finished = True
            self.conductor.notify()

    def go(self):
        if self.finished:
            return

        if self.thread is None:
            self.thread = threading.Thread(target=self._run)
            self.thread.start()

        else:
            self.conductor.go()

        self.conductor.wait()

        if self.error:
            raise self.error

    def finish(self):
        while not self.finished:
            try:
                self.go()
            except Exception:
                pass


class _permutations:
    """Generates a sequence of all permutations of `sequence`.

    Permutations are returned in lexicographic order using the "Generation in
    lexicographic order" algorithm described in `the Wikipedia article on "Permutation"
    <https://en.wikipedia.org/wiki/Permutation>`_.

    This implementation differs significantly from `itertools.permutations` in that the
    value of individual elements is taken into account, thus eliminating redundant
    orderings that would be produced by `itertools.permutations`.

    Args:
        sequence (Sequence[Any]): Sequence must be finite and orderable.

    Returns:
        Sequence[Sequence[Any]]: Set of all permutations of `sequence`.
    """

    def __init__(self, sequence):
        self._start = tuple(sorted(sequence))

    def __len__(self):
        """Compute the number of permutations.

        Let the number of elements in a sequence N and the number of repetitions for
        individual members of the sequence be n1, n2, ... nx. The number of unique
        permutations is: N! / n1! / n2! / ... / nx!.

        For example, let `sequence` be [1, 2, 3, 1, 2, 3, 1, 2, 3]. The number of unique
        permutations is: 9! / 3! / 3! / 3! = 1680.

        See: "Permutations of multisets" in `the Wikipedia article on "Permutation"
        <https://en.wikipedia.org/wiki/Permutation>`_.
        """
        repeats = [len(list(group)) for value, group in itertools.groupby(self._start)]
        length = math.factorial(len(self._start))
        for repeat in repeats:
            length /= math.factorial(repeat)

        return int(length)

    def __iter__(self):
        """Iterate over permutations.

        See: "Generation in lexicographic order" algorithm described in `the Wikipedia
        article on "Permutation" <https://en.wikipedia.org/wiki/Permutation>`_.
        """
        current = list(self._start)
        size = len(current)

        while True:
            yield tuple(current)

            # 1. Find the largest index i such that a[i] < a[i + 1].
            for i in range(size - 2, -1, -1):
                if current[i] < current[i + 1]:
                    break

            else:
                # If no such index exists, the permutation is the last permutation.
                return

            # 2. Find the largest index j greater than i such that a[i] < a[j].
            for j in range(size - 1, i, -1):
                if current[i] < current[j]:
                    break

            else:  # pragma: NO COVER
                raise RuntimeError("Broken algorithm")

            # 3. Swap the value of a[i] with that of a[j].
            temp = current[i]
            current[i] = current[j]
            current[j] = temp

            # 4. Reverse the sequence from a[i + 1] up to and including the final
            # element a[n].
            current = current[: i + 1] + list(reversed(current[i + 1 :]))
