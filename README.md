RELEASE ENGINE CORE
-------------------

[![Build Status](https://api.travis-ci.org/RHInception/re-core.png)](https://travis-ci.org/RHInception/re-core/)

This is the **core** component of the Inception Release Engine. The
core is essentially a finite state machine (**FSM**) hooked into a
message bus and a database.

The core oversees the execution of all *release steps* for any given
project. The core is separate from the actual execution of each
release step. Execution is delegated to the **worker** component.

For documentation see the [Read The Docs](http://release-engine.readthedocs.org/en/latest/components/recore.html) documentation.
