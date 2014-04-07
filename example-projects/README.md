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

Following the completion of the previous two steps one final step
happens:

* **List the tmp directory**

This step takes place only after both of the previous steps complete.
