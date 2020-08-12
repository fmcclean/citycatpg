from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from psycopg2.extensions import connection
import uuid
from psycopg2 import sql
from citycatio import Model
import pandas as pd
import rasterio as rio
import geopandas as gpd


@dataclass
class Run:
    run_duration: int
    srid: int
    resolution: int

    run_id: Optional[str] = field(default_factory=lambda: str(uuid.uuid1()))
    run_table: str = 'runs'
    run_name: str = ''
    run_start: Optional[datetime] = None
    run_end: Optional[datetime] = None
    output_frequency: int = 600

    domain_table: str = 'domain'
    domain_id: int = 1
    dem_table: str = 'dem'
    rain_table: Optional[str] = None
    rain_start: Optional[datetime] = None
    rain_end: Optional[datetime] = None

    rain_total: Optional[float] = None
    rain_duration: Optional[int] = None

    friction: float = 0.03

    green_areas_table: str = None
    buildings_table: str = None

    upload_url: Optional[str] = None
    hostname: Optional[str] = None
    version_number: Optional[str] = None

    model: Optional[Model] = None

    @property
    def rain_geom_table(self):
        if self.rain_table is not None:
            return self.rain_table + '_geom'

    def add(self, con: connection):

        query = sql.SQL("""
        CREATE TABLE IF NOT EXISTS {run_table} (
            run_id text,
            run_duration int, 
            srid int, 
            resolution int, 
            run_name text, 
            domain_table text,
            rain_table text,
            rain_start timestamp,
            rain_end timestamp,
            output_frequency int,
            rain_total numeric,
            rain_duration int,
            friction numeric,
            green_areas_table text,
            buildings_table text,
            upload_url text,
            hostname text,
            version_number text
        );
        
        INSERT INTO {run_table} (
            run_id,
            run_duration, 
            srid, 
            resolution, 
            run_name, 
            domain_table,
            rain_table,
            rain_start,
            rain_end,
            output_frequency,
            rain_total,
            rain_duration,
            friction,
            green_areas_table,
            buildings_table,
            upload_url,
            hostname,
            version_number
        ) 
        VALUES (
            %(run_id)s,
            %(run_duration)s, 
            %(srid)s, 
            %(resolution)s, 
            %(run_name)s, 
            %(domain_table)s,
            %(rain_table)s,
            %(rain_start)s,
            %(rain_end)s,
            %(output_frequency)s,
            %(rain_total)s,
            %(rain_duration)s,
            %(friction)s,
            %(green_areas_table)s,
            %(buildings_table)s,
            %(upload_url)s,
            %(hostname)s,
            %(version_number)s
        )
        """).format(run_table=sql.Identifier(self.run_table))
        with con:
            with con.cursor() as cur:
                cur.execute(query, self.__dict__)

    def get_model(self, con):

        rainfall_polygons = self.get_rainfall_polygons(con)
        if rainfall_polygons is not None:
            gids = rainfall_polygons.gid.unique().tolist()
        else:
            gids = None

        self.model = Model(
            dem=self.get_dem(con),
            rainfall=self.get_rainfall(con, gids),
            rainfall_polygons=rainfall_polygons,
            duration=self.run_duration,
            output_interval=self.output_frequency
        )

    def get_dem(self, con):

        with con:
            with con.cursor() as cursor:
                cursor.execute(sql.SQL("""
                SELECT ST_AsGDALRaster(ST_Union(ST_Clip(rast, geom)), 'GTiff') 
                FROM {dem_table}, {domain_table} WHERE ST_Intersects(rast, geom) and gid=%(domain_id)s
                """).format(
                    dem_table=sql.Identifier(self.dem_table),
                    domain_table=sql.Identifier(self.domain_table),
                ), self.__dict__)

                return rio.MemoryFile(cursor.fetchone()[0].tobytes())

    def get_rainfall(self, con, gids=None):

        if gids is None:

            rain = pd.DataFrame({
                'rainfall': [self.rain_total] * 2
            },
                index=[0, self.rain_duration])

            rain /= 1000  # convert from mm to m

        else:
            assert self.rain_start and self.rain_end

            rain = pd.read_sql_query(sql.SQL("""
            SELECT gid, value, time
            FROM {rain_table} WHERE gid = ANY({gids}) 
            AND time >= {rain_start} AND time <= {rain_end}
            """).format(
                rain_table=sql.Identifier(self.rain_table),
                gids=sql.Literal(gids),
                rain_start=sql.Literal(self.rain_start),
                rain_end=sql.Literal(self.rain_end),
            ), con)
            rain = rain.pivot(index='time', values='value', columns='gid')

            rain.index = (rain.index - rain.index[0]).total_seconds().astype(int)

        return rain

    def get_rainfall_polygons(self, con):
        if self.rain_total:
            return

        else:
            return gpd.GeoDataFrame.from_postgis(
                sql.SQL(
                """
                SELECT {rain_geom_table}.gid, {rain_geom_table}.geom FROM {rain_geom_table}, {domain_table} 
                WHERE ST_Intersects({rain_geom_table}.geom, {domain_table}.geom)
                """).format(
                    rain_geom_table=sql.Identifier(self.rain_geom_table),
                    domain_table=sql.Identifier(self.domain_table)
                ).as_string(con),
                con)


def fetch(con, run_id, run_table='runs'):
    query = sql.SQL("""
    SELECT 
        run_id,
        run_duration, 
        srid, 
        resolution, 
        run_name, 
        domain_table,
        rain_table,
        rain_start,
        rain_end,
        output_frequency,
        rain_total,
        rain_duration,
        friction,
        green_areas_table,
        buildings_table,
        upload_url,
        hostname,
        version_number
    
    FROM {run_table}
    WHERE run_id = %(run_id)s
    """).format(run_table=sql.Identifier(run_table))
    with con:
        with con.cursor() as cur:
            cur.execute(query, dict(run_id=run_id))
            (
                run_id,
                run_duration,
                srid,
                resolution,
                run_name,
                domain_table,
                rain_table,
                rain_start,
                rain_end,
                output_frequency,
                rain_total,
                rain_duration,
                friction,
                green_areas_table,
                buildings_table,
                upload_url,
                hostname,
                version_number
            ) = cur.fetchone()

    return Run(
        run_id=run_id,
        run_duration=run_duration,
        srid=srid,
        resolution=resolution,
        run_name=run_name,
        domain_table=domain_table,
        rain_table=rain_table,
        rain_start=rain_start,
        rain_end=rain_end,
        output_frequency=output_frequency,
        rain_total=rain_total,
        rain_duration=rain_duration,
        friction=friction,
        green_areas_table=green_areas_table,
        buildings_table=buildings_table,
        upload_url=upload_url,
        hostname=hostname,
        version_number=version_number
    )
