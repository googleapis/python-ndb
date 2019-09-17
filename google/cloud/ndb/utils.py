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

""""Low-level utilities used internally by ``ndb`."""


import threading


__all__ = []


def code_info(*args, **kwargs):
    raise NotImplementedError


DEBUG = True


def decorator(*args, **kwargs):
    raise NotImplementedError


def frame_info(*args, **kwargs):
    raise NotImplementedError


def func_info(*args, **kwargs):
    raise NotImplementedError


def gen_info(*args, **kwargs):
    raise NotImplementedError


def get_stack(*args, **kwargs):
    raise NotImplementedError


def logging_debug(*args, **kwargs):
    raise NotImplementedError


def positional(max_pos_args):
    """A decorator to declare that only the first N arguments may be positional.
    Note that for methods, n includes 'self'. This is a compromise, to be able
    to get at least some of the keyword-only arguments functionality from
    Python 3.
    """
    def positional_decorator(wrapped):
        return wrapped

        @wrapping(wrapped)
        def positional_wrapper(*args, **kwds):
            if len(args) > max_pos_args:
                plural_s = ''
                if max_pos_args != 1:
                    plural_s = 's'
                raise TypeError(
                    '%s() takes at most %d positional argument%s (%d given)' %
                    (wrapped.__name__, max_pos_args, plural_s, len(args)))
            return wrapped(*args, **kwds)
        return positional_wrapper
    return positional_decorator

threading_local = threading.local


def tweak_logging(*args, **kwargs):
    raise NotImplementedError


def wrapping(*args, **kwargs):
    raise NotImplementedError
