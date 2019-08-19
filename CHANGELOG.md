# Changelog

[PyPI History][1]

[1]: https://pypi.org/project/google-cloud-ndb/#history

## 0.1.0

08-19-2019 15:06 PDT

- Implement ``Context.call_on_commit``. ([#159](https://github.com/googleapis/python-ndb/pull/159))
- Implement ``Context.flush`` ([#158](https://github.com/googleapis/python-ndb/pull/158))
- Implement ``use_datastore`` flag. ([#155](https://github.com/googleapis/python-ndb/pull/155))
- Implement ``tasklets.toplevel``. ([#157](https://github.com/googleapis/python-ndb/pull/157))
- remove skip flag accidentally left over ([#154](https://github.com/googleapis/python-ndb/pull/154))
- Update Migration Notes. ([#152](https://github.com/googleapis/python-ndb/pull/152))
- fix polymodel put and get ([#151](https://github.com/googleapis/python-ndb/pull/151))
- try to get kokoro to add indexes for system tests ([#145](https://github.com/googleapis/python-ndb/pull/145))
- add project_urls for pypi page ([#144](https://github.com/googleapis/python-ndb/pull/144))
- RedisCache ([#150](https://github.com/googleapis/python-ndb/pull/150))
- Implement Global Cache (memcache) ([#148](https://github.com/googleapis/python-ndb/pull/148))
- Fix TRAMPOLINE_BUILD_FILE in docs/common.cfg. ([#143](https://github.com/googleapis/python-ndb/pull/143))
- Add kokoro docs job to publish to googleapis.dev. ([#142](https://github.com/googleapis/python-ndb/pull/142))
- check for required properties before put
- initial version of migration guide ([#121](https://github.com/googleapis/python-ndb/pull/121))
- _prepare_for_put was not being called at entity level ([#138](https://github.com/googleapis/python-ndb/pull/138))
- Fix key property. ([#136](https://github.com/googleapis/python-ndb/pull/136))
- add system test for PolyModel ([#133](https://github.com/googleapis/python-ndb/pull/133))
- ask for feature development coordination via issues
- Fix thread local context. ([#131](https://github.com/googleapis/python-ndb/pull/131))
- Bugfix: Respect ``_indexed`` flag of properties. ([#127](https://github.com/googleapis/python-ndb/pull/127))
- Backwards compatibility with older style structured properties. ([#126](https://github.com/googleapis/python-ndb/pull/126))
- add spellcheck sphinx extension to docs build process ([#123](https://github.com/googleapis/python-ndb/pull/123))
- Fix system test under Datastore Emulator. (Fixes [#118](https://github.com/googleapis/python-ndb/pull/118)) ([#119](https://github.com/googleapis/python-ndb/pull/119))
- add unit tests for _entity_from_ds_entity expando support ([#120](https://github.com/googleapis/python-ndb/pull/120))
- ndb.Expando properties load and save ([#117](https://github.com/googleapis/python-ndb/pull/117))
- Implement cache policy. ([#116](https://github.com/googleapis/python-ndb/pull/116))

### Implementation Changes

### New Features

### Dependencies

### Documentation

### Internal / Testing Changes

## 0.0.1

06-11-2019 16:30 PDT

### Implementation Changes
- Query repeated structured properties. ([#103](https://github.com/googleapis/python-ndb/pull/103))
- Fix Structured Properties ([#102](https://github.com/googleapis/python-ndb/pull/102))

### New Features
- Implement expando model ([#99](https://github.com/googleapis/python-ndb/pull/99))
- Model properties ([#96](https://github.com/googleapis/python-ndb/pull/96))
- Implemented tasklets.synctasklet ([#58](https://github.com/googleapis/python-ndb/pull/58))
- Implement LocalStructuredProperty ([#93](https://github.com/googleapis/python-ndb/pull/93))
- Implement hooks. ([#95](https://github.com/googleapis/python-ndb/pull/95))
- Three easy Model methods. ([#94](https://github.com/googleapis/python-ndb/pull/94))
- Model.get or insert ([#92](https://github.com/googleapis/python-ndb/pull/92))
- Implement ``Model.get_by_id`` and ``Model.get_by_id_async``.
- Implement ``Model.allocate_ids`` and ``Model.allocate_ids_async``.
- Implement ``Query.fetch_page`` and ``Query.fetch_page_async``.
- Implement ``Query.count`` and ``Query.count_async``
- Implement ``Query.get`` and ``Query.get_async``.

### Documentation
- update sphinx version and eliminate all warnings ([#105](https://github.com/googleapis/python-ndb/pull/105))

## 0.0.1dev1

Initial development release of NDB client library.
