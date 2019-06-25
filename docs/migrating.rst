######################################
Migrating from Python 2 version of NDB
######################################

While every attempt has been made to keep compatibilty with the previous
version of `ndb`, there are fundamental differences at the platform level,
which have made necessary in some cases to depart from the original
implementation, and sometimes even to remove exisitng functionality
altogether.

Because one of the main objectives of this rewrite was to be able to use `ndb`
independently from Google App Engine, the legacy APIs from GAE cannot be
depended upon. Also, any environment and runtime variables and resources will
not be available when running outside of GAE. This means that many `ndb` APIs
that depended on GAE have been changed, and many APIs that accessed GAE
resources directly have been dropped.

Aside from this, there are many differences between the Datastore APIs
provided by GAE and those provided by the newer Google Cloud Platform. These
diffeences have required some code and API changes as well.

Finally, in many cases, new features of Python 3 have eliminated the need for
some code, particularly from the old `utils` module.

If you are migrating code, these changes can generate some confusion. This
document will cover the most common migration issues.

Setting up a connection
=======================

The most important difference from the previous `ndb` version, is that the new
`ndb` requires the use of a client to set up a runtime context for a project.
This is necessary because `ndb` can now be used in any Python environment, so
we can no longer assume it's running in the context of a GAE request.

The `ndb` client uses ``google.auth`` for authentication, which is how APIs in
Google Cloud Platform work. The client can take a `credentials` parameter or
get the credentials using the `GOOGLE_APPLCATION_CREDENTIALS` environment
variable, which is the recommended option.

After instantiating a client, it's necessary to establish a runtime context,
using the ``Client.context`` method. All interactions with the database must
be within the context obtained from this call::

    from google.cloud import ndb

    client = ndb.Client()

    with context as client.context():
        do_something_with_ndb()

Note that the example above is assumming the google credentials are set in
the environment.

Keys
====

There are some methods from the ``key`` module that are not implemented in
this version of `ndb`:

    - Key.from_old_key.
    - Key.to_old_key.

Properties
==========

There are various small changes in some of the model properties that might
trip you up when migrating code. Here are some of them, for quick reference:

- The `BlobProperty` constructor only sets `_compressed` if explicitly
  passed. The original set `_compressed` always.
- In the exact same fashion the `JsonProperty` constructor only sets
  `_json_type` if explicitly passed.]
- Similarly, the `DateTimeProperty` constructor only sets `_auto_now` and
  `_auto_now_add` if explicitly passed.
- `TextProperty(indexed=True)` and `StringProperty(indexed=False)` are no
  longer supported.
- The `Property()` constructor (and subclasses) originally accepted both
  `unicode` and `str` (the Python 2 versions) for `name` (and `kind`) but now
  only accept `str`.

QueryOptions and Query Order
============================

The QueryOptions class from ``google.cloud.ndb.query``, has been reimplemented,
since ``google.appengine.datastore.datastore_rpc.Configuration`` is no longer
available. It still uses the same signature, but does not support original
Configuration methods.

Similarly,b ecause ``google.appengine.datastore.datastore_query.Order`` is no
longer available, the ``ndb.query.PropertyOrder`` class has been created to
replace it.

MessageProperty and EnumProperty
================================

These properties, from the ``ndb.msgprop`` module, depend on the Google
Protocol RPC Library, or `protorpc`, which is not an `ndb` dependency. For
this reason, they are not part of this version of `ndb`.

Tasklets
========

When writing a `tasklet`, it is no longer necessary to raise a Return
exception for returning the result. A normal return can be used instead::

    @ndb.tasklet
    def get_cart():
        cart = yield CartItem.query().fetch_async()
        return cart

Note that "raise Return(cart)" can still be used, but it's not recommended.

There are some methods from the ``tasklet`` module that are not implemented in
this version of `ndb`, mainly because of changes in how an `ndb` context is
created and used in this version:

    - add_flow_exception.
    - make_context.
    - make_default_context.
    - QueueFuture.
    - ReducedFuture.
    - SerialQueueFuture.
    - set_context.
    - toplevel.

Utils
=====

The previous version of `ndb` included an ``ndb.utils`` module, which defined
a number of methods that were mostly used internally. Some of those have been
made obsolete by new Python 3 features, while others have been discarded due
to implementation differences in the new `ndb`.

Possibly the most used utility from this module outside of `ndb` code, is the
``positional`` decorator, which declares that only the first `n` arguments of
a function or method may be positional. Python 3 can do this using keyword-only
arguments. What used to be written as::

    @utils.positional(2)
    def function1(arg1, arg2, arg3=None, arg4=None)
        pass

Will be written like this in the new version::

    def function1(arg1, arg2, *, arg3=None, arg4=None)
        pass

Exceptions
==========

App Engine's legacy exceptions are no longer available, but `ndb` provides
shims for most of them, which can be imported from the `ndb.exceptions`
package, like this::

    from ndb.exceptioms import BadRequestError, BadArgumentError

Datastore API
=============

There are many differences bewteen the current Datastore API and the legacy App
Engine Datastore. In most cases, where the public API was generally used, this
should not be a problem. However, if you relied in your code on the private
Datastore API, the code that does this will probably need to be rewritten.
Specifically, any function or method that dealt directly with protocol buffers
will no longer work. The Datastore `.protobuf` definitions have changed
significantly from the public API used by App Engine to the current published
API. Additionally, this version of NDB mostly delegates to
`google.cloud.datastore` for parsing data returned by RPCs, which is a
significant internal refactoring.

Default Namespace
=================

In the previous version, ``google.appengine.api.namespacemanager`` was used
to determine the default namespace when not passed in to constructors which
require it, like ``Key``. In this version, the client class can be instantiated
with a namespace, which will be used as the default whenever it's not included
in the constuctor or method arguments that expect a namespace::

    from google.cloud import ndb

    client=ndb.Client(namespace="my namespace")
    
    with context as client.context():
        key = ndb.Key("SomeKind", "SomeId")

In this example, the key will be created under the namespace `my namespace`,
because that's the namespace passed in when setting up the client.

Django Middleware
=================

The Django middleware that was part of the GAE version of `ndb` has been
discontinued and is no longer available in current `ndb`. The middleware
basically took care of setting the context, which can be accomplished on
modern Django with a simple class middleware, similar to this::

    from google.cloud import ndb

    class NDBMiddleware(object):
        def __init__(self, get_response):
            self.get_response = get_response
            client = ndb.Client()
            self.ndb_context = client.context()

        def __call__(self, request):
            request.ndb_context = self.ndb_context
            response = self.get_response(request)
            return response

The ``__init__`` method is called only once, during server start, so it's a
good place to create and store an `ndb` context. The ``__call__`` method will
be called once for every request, so we add our ndb context to the request
there, before the response is processed. The context will then be available in
view and template code.

Another way to get an `ndb` context into a request, would be to use a `context
processor`, but those are functions called for every request, which means we
would need to initialize the client and context on each request, or find
another way to initialize and get the initial context.

Note that the above code, like other `ndb` code, assumes the presence of the
`GOOGLE_APPLCATION_CREDENTIALS` environment variable when the client is
created. See Django documentation for details on setting up the environment.
