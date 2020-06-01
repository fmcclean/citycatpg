from citycatio import Model
import rasterio as rio
import pandas as pd


def read_postgis(con, domain_table: str = 'domain', domain_id: int = 1, dem_table: str = 'dem'):
    with con.cursor() as cursor:
        cursor.execute("""
        SELECT ST_AsGDALRaster(ST_Union(ST_Clip(rast, geom)), 'GTiff') 
        FROM {}, {} WHERE ST_Intersects(rast, geom) and gid={}
        """.format(dem_table, domain_table, domain_id))

        dem = rio.MemoryFile(cursor.fetchone()[0].tobytes())

    return Model(dem=dem, rainfall=pd.DataFrame([0]))
