RELEASE ENGINE CORE
-------------------

[![Build Status](https://api.travis-ci.org/RHInception/re-core.png)](https://travis-ci.org/RHInception/re-core/)

This is the **core** component of the Inception Release Engine. The
core is essentially a finite state machine (**FSM**) hooked into a
message bus and a database.

The core oversees the execution of all *release steps* for any given
project. The core is separate from the actual execution of each
release step. Execution is delegated to the **worker** component.


DEPENDENCIES
------------

State is maintained both in-memory, and persistently in **MongoDB**.

The core communicates over a **RabbitMQ** message bus. This is how new
job orders are received, tasks are delegated, and workers communicate
release step progress.

The FSM utilizes the [pika](https://github.com/pika/pika/) library to
interact with **RabbitMQ**. You'll need at least **version 0.9.13**
installed.


RUNNING FROM SOURCE
-------------------

````bash
$ . ./hacking/setup-env
$ re-core -c ./examples/settings-example.json
````

CONFIGURATION
-------------

Configuration of the server is done in JSON. You can find an example
configuration file in the `examples/` directory.

You can point to a specific configuration file using the `-c`
command-line option.


| Name     | Type | Parent | Value                                      |
|----------|------|--------|--------------------------------------------|
| LOGFILE  | str  | None   | File name for the application level log    |
| MQ       | dict | None   | Where all of the MQ connection settings are|
| SERVER   | str  | MQ     | Hostname or IP of the server               |
| NAME     | str  | MQ     | Username to connect with                   |
| PASSWORD | str  | MQ     | Password to authenticate with              |
| QUEUE    | str  | MQ     | Queue on the server to bind                |
| DB       | dict | None   | Where all the DB connection settings are   |
| SERVERS  | list | DB     | List of all of the MongoDB hostname/IPs    |
| DATABASE | str  | DB     | Name of the MongoDB database               |
| NAME     | str  | DB     | Username to connect with                   |
| PASSWORD | str  | DB     | Password to authenticate with              |


### Example Config

```json
{
    "LOGFILE": "recore.log",
    "MQ": {
        "SERVER": "127.0.0.1",
        "NAME": "guest",
        "PASSWORD": "guest1",
        "QUEUE": "re"
    },
    "DB": {
        "SERVERS": [
            "mongo.example.com",
            "mongo-failover.example.com"
        ],
        "DATABASE": "re",
        "NAME": "lord_mongo",
        "PASSWORD": "websc@l3"
    }
}
```
