# Copyright 2021 Google LLC
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

import pytest

from . import orchestrate


def test__permutations():
    sequence = [1, 2, 3, 1, 2, 3, 1, 2, 3]
    permutations = orchestrate._permutations(sequence)
    assert len(permutations) == 1680

    result = list(permutations)
    assert len(permutations) == len(result)  # computed length matches reality
    assert len(result) == len(set(result))  # no duplicates
    assert result[0] == (1, 1, 1, 2, 2, 2, 3, 3, 3)
    assert result[-1] == (3, 3, 3, 2, 2, 2, 1, 1, 1)

    assert list(orchestrate._permutations([1, 2, 3])) == [
        (1, 2, 3),
        (1, 3, 2),
        (2, 1, 3),
        (2, 3, 1),
        (3, 1, 2),
        (3, 2, 1),
    ]


class Test_orchestrate:
    @staticmethod
    def test_no_failures():
        test_calls = []

        def make_test(name):
            def test():
                test_calls.append(name)
                orchestrate.syncpoint()
                test_calls.append(name)
                orchestrate.syncpoint()
                test_calls.append(name)

            return test

        test1 = make_test("A")
        test2 = make_test("B")

        permutations = orchestrate._permutations(["A", "B", "A", "B", "A", "B"])
        expected = list(itertools.chain(*permutations))

        counts = orchestrate.orchestrate(test1, test2)
        assert counts == (3, 3)
        assert test_calls == expected

    @staticmethod
    def test_syncpoints_decrease_after_initial_run():
        test_calls = []

        def make_test(name):
            syncpoints = [name] * 4

            def test():
                test_calls.append(name)
                if syncpoints:
                    orchestrate.syncpoint()
                    test_calls.append(syncpoints.pop())

            return test

        test1 = make_test("A")
        test2 = make_test("B")

        expected = [
            "A",
            "A",
            "B",
            "B",
            "A",
            "B",
            "A",
            "B",
            "A",
            "B",
            "B",
            "A",
            "B",
            "A",
            "A",
            "B",
            "B",
            "A",
            "B",
            "A",
        ]

        counts = orchestrate.orchestrate(test1, test2)
        assert counts == (2, 2)
        assert test_calls == expected

    @staticmethod
    def test_syncpoints_increase_after_initial_run():
        test_calls = []

        def make_test(name):
            syncpoints = [None] * 4

            def test():
                test_calls.append(name)
                orchestrate.syncpoint()
                test_calls.append(name)

                if syncpoints:
                    syncpoints.pop()
                else:
                    orchestrate.syncpoint()
                    test_calls.append(name)

            return test

        test1 = make_test("A")
        test2 = make_test("B")

        expected = [
            "A",
            "A",
            "B",
            "B",
            "A",
            "B",
            "A",
            "B",
            "A",
            "B",
            "B",
            "A",
            "B",
            "A",
            "A",
            "B",
            "B",
            "A",
            "B",
            "A",
            "A",
            "B",
            "B",
            "B",
            "A",
            "A",
            "A",
            "B",
        ]

        counts = orchestrate.orchestrate(test1, test2)
        assert counts == (2, 2)
        assert test_calls == expected

    @staticmethod
    def test_failure():
        test_calls = []

        def make_test(name):
            syncpoints = [None] * 4

            def test():
                test_calls.append(name)
                orchestrate.syncpoint()
                test_calls.append(name)

                if syncpoints:
                    syncpoints.pop()
                else:
                    assert True is False

            return test

        test1 = make_test("A")
        test2 = make_test("B")

        expected = [
            "A",
            "A",
            "B",
            "B",
            "A",
            "B",
            "A",
            "B",
            "A",
            "B",
            "B",
            "A",
            "B",
            "A",
            "A",
            "B",
            "B",
            "A",
            "B",
            "A",
        ]

        with pytest.raises(AssertionError):
            orchestrate.orchestrate(test1, test2)

        assert test_calls == expected
