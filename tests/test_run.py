from citycatpg import Run, fetch
from unittest import TestCase
from shapely.geometry import Polygon
import rasterio as rio
from rasterio.transform import Affine
import numpy as np
import psycopg2
from psycopg2 import sql

con = psycopg2.connect(database='postgres', user='postgres', password='password', host='localhost')
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


class TestRun(TestCase):

    def test_add_run(self):
        with con:
            with con.cursor() as cur:
                cur.execute('DROP TABLE IF EXISTS runs')

        Run(run_duration=500, srid=3035, resolution=90).add(con)

    def test_fetch(self):
        with con:
            with con.cursor() as cur:
                cur.execute('DROP TABLE IF EXISTS runs')

        r = Run(run_duration=500, srid=3035, resolution=90)
        r.add(con)

        fetch(con, run_id=r.run_id)

    def test_get_model(self):
        dem_file.seek(0)
        r = Run(100, 3035, 90)
        with con:
            with con.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis_raster")
                cursor.execute("SET postgis.gdal_enabled_drivers TO 'GTiff'")

                cursor.execute(
                    sql.SQL("""
                        DROP TABLE IF EXISTS {domain_table};
                        CREATE TABLE {domain_table} (gid serial PRIMARY KEY, geom geometry);
                        INSERT INTO {domain_table} (geom) VALUES (ST_GeomFromText(%(geom)s));
                        DROP TABLE IF EXISTS {dem_table};
                        CREATE TABLE {dem_table} (rast raster);
                        INSERT INTO {dem_table}(rast) VALUES (ST_FromGDALRaster(%(rast)s));
                    """).format(domain_table=sql.Identifier(r.domain_table), dem_table=sql.Identifier(r.dem_table)),
                    dict(
                        geom=str(Polygon(
                            [[x_min, y_min], [x_min, y_max], [x_max / 2, y_max / 2], [x_max, y_min], [x_min, y_min]])),
                        rast=psycopg2.Binary(dem_file.read())))

        r.get_model(con)
        r.model.write('tests/test_model')
