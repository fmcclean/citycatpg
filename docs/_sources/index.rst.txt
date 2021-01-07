.. Citycatpg documentation master file, created by
   sphinx-quickstart on Tue Jan  5 12:07:08 2021.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Citycatpg's documentation!
=====================================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

Citycatpg creates and runs CityCAT models with data and parameters stored in a PostgreSQL database.
RabbitMQ is used to distribute model runs across multiple servers.

.. image:: network-diagram.svg

Domain boundaries, DEMs, rainfall, green areas and buildings are stored in tables as PostGIS geometries and rasters.
Table names associated with each data source are stored with each run configuration.
Green areas and buildings table names are optional and a rainfall table is only required if rainfall amount and
duration are not specified.
The domain table can contain multiple boundaries while each run only uses a single polygon,
therefore a domain ID is required.
The rainfall table contains time series' with matching frequencies and start times, stored in a separate metadata table.

.. image:: schema.svg

citycatpg module
--------------------
.. automodule:: citycatpg
   :members:
   :member-order: bysource



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
