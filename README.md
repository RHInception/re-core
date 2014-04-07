RELEASE ENGINE CORE
-------------------

This is the **core** component of the Inception Release Engine. The
core is essentially a finite state machine hooked into a message bus
and a database.

The core oversees the execution of all *release steps* for any given
project. The core is separate from the actual execution of each
release step. Execution is delegated to the **worker** component.


DEPENDENCIES
------------

State is maintained both in-memory, and persistently in **MongoDB**.

The core communicates over a **RabbitMQ** message bus. This is how new
job orders are received, tasks are delegated, and workers communicate
release step progress.
