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

"""Retry functions."""

import functools
import grpc
import itertools

from google.api_core import retry as core_retry
from google.api_core import exceptions as core_exceptions
from google.cloud.ndb import tasklets

_DEFAULT_INITIAL_DELAY = 1.0  # seconds
_DEFAULT_MAXIMUM_DELAY = 60.0  # seconds
_DEFAULT_DELAY_MULTIPLIER = 2.0
_DEFAULT_RETRIES = 3


def retry_async(callback, retries=_DEFAULT_RETRIES):
    """Decorator for retrying functions or tasklets asynchronously.

    The `callback` will be called up to `retries + 1` times. Any transient
    API errors (internal server errors) raised by `callback` will be caught and
    `callback` will be retried until the call either succeeds, raises a
    non-transient error, or the number of retries is exhausted.

    See: :func:`google.api_core.retry.if_transient_error` for information on
    what kind of errors are considered transient.

    Args:
        callback (Callable): The function to be tried. May be a tasklet.
        retries (Integer): Number of times to retry `callback`. Will try up to
            `retries + 1` times.

    Returns:
        tasklets.Future: Result will be the return value of `callback`.
    """

    @tasklets.tasklet
    @functools.wraps(callback)
    def retry_wrapper(*args, **kwargs):
        sleep_generator = core_retry.exponential_sleep_generator(
            _DEFAULT_INITIAL_DELAY,
            _DEFAULT_MAXIMUM_DELAY,
            _DEFAULT_DELAY_MULTIPLIER,
        )

        for sleep_time in itertools.islice(sleep_generator, retries + 1):
            try:
                result = callback(*args, **kwargs)
                if isinstance(result, tasklets.Future):
                    result = yield result
                return result
            except Exception as e:
                # `e` is removed from locals at end of block
                error = e  # See: https://goo.gl/5J8BMK
                if not is_transient_error(error):
                    raise

            yield tasklets.sleep(sleep_time)

        raise core_exceptions.RetryError(
            "Maximum number of {} retries exceeded while calling {}".format(
                retries, callback
            ),
            cause=error,
        )

    return retry_wrapper


TRANSIENT_CODES = (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.INTERNAL)


def is_transient_error(error):
    """Determine whether an error is transient.

    Returns:
        bool: True if error is transient, else False.
    """
    if core_retry.if_transient_error(error):
        return True

    method = getattr(error, "code", None)
    if method is not None:
        code = method()
        return code in TRANSIENT_CODES

    return False
