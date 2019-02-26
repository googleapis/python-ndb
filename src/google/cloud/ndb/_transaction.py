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

from google.cloud.ndb import context as context_module
from google.cloud.ndb import _datastore_api
from google.cloud.ndb import tasklets


def transaction(callback, retries=0, read_only=False):
    future = transaction_async(callback, retries=retries, read_only=read_only)
    return future.result()


@tasklets.tasklet
def transaction_async(callback, retries=0, read_only=False):
    if retries:
        raise NotImplementedError("Retry is not implemented yet")

    # Keep transaction propagation simple: don't do it.
    context = context_module.get_context()
    if context.transaction:
        raise NotImplementedError(
            "Can't start a transaction during a transaction."
        )

    # Start the transaction
    transaction_id = yield _datastore_api.begin_transaction(read_only)

    with context.new(transaction=transaction_id).use():
        try:
            # Run the callback
            result = callback()
            if isinstance(result, tasklets.Future):
                result = yield result

            # Commit the transaction
            yield _datastore_api.commit(transaction_id)

        # Rollback if there is an error
        except:
            yield _datastore_api.rollback(transaction_id)
            raise

        return result
