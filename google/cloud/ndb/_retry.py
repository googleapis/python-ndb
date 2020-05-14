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


def wraps_safely(obj, attr_names=functools.WRAPPER_ASSIGNMENTS):
    """Python 2.7 functools.wraps has a bug where attributes like ``module``
    are not copied to the wrappers and thus cause attribute errors. This
    wrapper prevents that problem."""
    return functools.wraps(
        obj, assigned=(name for name in attr_names if hasattr(obj, name))
    )


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
    @wraps_safely(callback)
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
            except Exception as e:
                # `e` is removed from locals at end of block
                error = e  # See: https://goo.gl/5J8BMK
                if not is_transient_error(error):
                    raise error
            else:
                raise tasklets.Return(result)

            yield tasklets.sleep(sleep_time)

        raise core_exceptions.RetryError(
            "Maximum number of {} retries exceeded while calling {}".format(
                retries, callback
            ),
            cause=error,
        )

    return retry_wrapper


# Possibly we should include DEADLINE_EXCEEDED. The caveat is that I think the
# timeout is enforced on the client side, so it might be possible that a Commit
# request times out on the client side, but still writes data on the server
# side, in which case we don't want to retry, since we can't commit the same
# transaction more than once. Some more research is needed here. If we discover
# that a DEADLINE_EXCEEDED status code guarantees the operation was cancelled,
# then we can add DEADLINE_EXCEEDED to our retryable status codes. Not knowing
# the answer, it's best not to take that risk.
TRANSIENT_CODES = (
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.INTERNAL,
    grpc.StatusCode.ABORTED,
)


def is_transient_error(error):
    """Determine whether an error is transient.

    Returns:
        bool: True if error is transient, else False.
    """
    if core_retry.if_transient_error(error):
        return True

    if isinstance(error, grpc.Call):
        method = getattr(error, "code", None)
        if callable(method):
            code = method()
            return code in TRANSIENT_CODES

    return False
