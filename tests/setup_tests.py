from shapely.geometry import Polygon
import rasterio as rio
from rasterio.transform import Affine
import numpy as np
import psycopg2
from psycopg2 import sql
from citycatpg import Run

con = psycopg2.connect(database='test', user='postgres', password='password', host='localhost')

dem_file = rio.MemoryFile()
x_min, y_max, res, height, width = 100, 500, 5, 100, 200
x_max, y_min = x_min + width * res, y_max - height * res
array = np.round(np.random.random((height, width)), 3)

with rio.open(
        dem_file,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=1,
        dtype=array.dtype,
        transform=Affine.translation(x_min, y_max) * Affine.scale(res, -res),
        nodata=-9999
) as dst:
    dst.write(array, 1)

dem_file.seek(0)

r = Run(100, 3035, 90, rain_table='rain')

with con:
    with con.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis_raster")
        cursor.execute("SET postgis.gdal_enabled_drivers TO 'GTiff'")

        cursor.execute(
            sql.SQL(""" 
                        DROP TABLE IF EXISTS {domain_table};
                        CREATE TABLE {domain_table} (gid serial PRIMARY KEY, geom geometry);
                        INSERT INTO {domain_table} (gid, geom) VALUES (500, ST_GeomFromText(%(geom)s));

                        DROP TABLE IF EXISTS {rain_table};
                        CREATE TABLE {rain_table} (gid serial PRIMARY KEY, geom geometry, start timestamp, 
                        frequency interval, series numeric[]);
                        INSERT INTO {rain_table} (geom, series) 
                        VALUES (ST_GeomFromText(%(geom)s), '{{1, 2, 3, 4, 5}}');
                        
                        DROP TABLE IF EXISTS {metadata_table};
                        CREATE TABLE {metadata_table} (id serial PRIMARY KEY, dataset text, source text, 
                        frequency interval , start timestamp);
                        INSERT INTO {metadata_table} (dataset, frequency, start) VALUES 
                            ('rain', '1 day', '2000-01-01');

                        DROP TABLE IF EXISTS {dem_table};
                        CREATE TABLE {dem_table} (rast raster);
                        INSERT INTO {dem_table}(rast) VALUES (ST_FromGDALRaster(%(rast)s));
                    """).format(
                domain_table=sql.Identifier(r.domain_table),
                dem_table=sql.Identifier(r.dem_table),
                rain_table=sql.Identifier(r.rain_table),
                metadata_table=sql.Identifier(r.metadata_table),
            ),
            dict(
                geom=str(Polygon(
                    [[x_min, y_min], [x_min, y_max], [x_max / 2, y_max / 2], [x_max, y_min], [x_min, y_min]])),
                rast=psycopg2.Binary(dem_file.read())))
