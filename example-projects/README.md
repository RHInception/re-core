FILES
-----

**01.json**

Simple project with one step. That step lists the contents of the `/`
directory.

**02.json**

More complicated project with three steps.

The following two steps execute concurrently (because they are wrapped
in a list together):

* **Long-list the / directory**
* **List my home directory**

Take special note of the first step definition. Notice there is a new
key there now: `errors` and it has the value `ignore`. This means that
if the first step fails it will not stop the rest of the project steps
from running.


Following the completion of the previous two steps one final step
happens:

* **List the tmp directory**

This step takes place only after both of the previous steps complete.
