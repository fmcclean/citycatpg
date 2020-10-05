import shutil
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from psycopg2.extensions import connection
import uuid
from psycopg2 import sql
from citycatio import Model, output
import pandas as pd
import rasterio as rio
import geopandas as gpd
import os
import subprocess
import warnings


@dataclass
class Run:
    run_duration: int
    srid: int
    resolution: int

    run_id: Optional[str] = field(default_factory=lambda: str(uuid.uuid4()))
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

    metadata_table: str = 'metadata'

    version_number: Optional[str] = None

    model: Optional[Model] = None

    def add(self, con: connection):

        query = sql.SQL("""
        CREATE TABLE IF NOT EXISTS {run_table} (
            run_id text,
            run_duration int, 
            srid int, 
            resolution int, 
            run_name text, 
            domain_table text,
            dem_table text,
            rain_table text,
            rain_start timestamp,
            rain_end timestamp,
            output_frequency int,
            rain_total numeric,
            rain_duration int,
            friction numeric,
            green_areas_table text,
            buildings_table text,
            version_number text
        );
        
        INSERT INTO {run_table} (
            run_id,
            run_duration, 
            srid, 
            resolution, 
            run_name, 
            domain_table,
            dem_table,
            rain_table,
            rain_start,
            rain_end,
            output_frequency,
            rain_total,
            rain_duration,
            friction,
            green_areas_table,
            buildings_table,
            version_number
        ) 
        VALUES (
            %(run_id)s,
            %(run_duration)s, 
            %(srid)s, 
            %(resolution)s, 
            %(run_name)s, 
            %(domain_table)s,
            %(dem_table)s,
            %(rain_table)s,
            %(rain_start)s,
            %(rain_end)s,
            %(output_frequency)s,
            %(rain_total)s,
            %(rain_duration)s,
            %(friction)s,
            %(green_areas_table)s,
            %(buildings_table)s,
            %(version_number)s
        )
        """).format(run_table=sql.Identifier(self.run_table))
        with con:
            with con.cursor() as cur:
                cur.execute(query, self.__dict__)

    def get_model(self, con):

        assert self.rain_table is not None or self.rain_total is not None
        rainfall, rainfall_polygons = self.get_rainfall(con)
        self.model = Model(
            dem=self.get_dem(con),
            rainfall=rainfall,
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

    def get_rainfall(self, con):

        if self.rain_total is not None:

            rain = pd.DataFrame({
                'rainfall': [self.rain_total / self.rain_duration] * 2 + [0] * 2
            },
                index=[0, self.rain_duration, self.rain_duration + 1, self.rain_duration + 2])

            rain /= 1000  # convert from mm to m

            return rain, None

        else:
            assert self.rain_start and self.rain_end

            with con.cursor() as cur:
                cur.execute(
                    sql.SQL('select start, frequency from {metadata_table} where dataset = %(dataset)s').format(
                        metadata_table=sql.Identifier(self.metadata_table)),
                    dict(dataset=self.rain_table)
                )
                start, frequency = cur.fetchone()

            idx_min = ((self.rain_start-start) / frequency) + 1
            idx_max = ((self.rain_end-start) / frequency) + 1

            rain = gpd.GeoDataFrame.from_postgis(sql.SQL("""
            SELECT {rain_table}.geom, series[{idx_min}:{idx_max}]
            FROM {rain_table}, {domain_table}
            WHERE ST_Intersects({rain_table}.geom, {domain_table}.geom)
            """).format(
                idx_min=sql.Literal(idx_min),
                idx_max=sql.Literal(idx_max),
                rain_table=sql.Identifier(self.rain_table),
                rain_start=sql.Literal(self.rain_start),
                rain_end=sql.Literal(self.rain_end),
                domain_table=sql.Identifier(self.domain_table)
            ).as_string(con), con)
            geom = rain.geom
            rain = rain.series.explode()
            rain = pd.DataFrame({'values': rain.values, 'index': list(range(len(rain[0]))) * len(geom),
                                'columns': rain.index}).pivot(values='values', index='index', columns='columns')
            rain = rain.astype(float) / frequency.total_seconds() / 1000
            rain.index = pd.date_range(start=self.rain_start, freq=frequency, periods=len(rain))
            rain.index = (rain.index - rain.index[0]).total_seconds().astype(int)

            return rain if type(rain) == pd.DataFrame else rain.to_frame(), geom

    def execute(self, run_path, out_path):

        self.model.write(run_path)

        executable = os.getenv('CITYCAT')
        if executable is None:
            warnings.warn('CITYCAT environment variable missing')
            return
        shutil.copy(executable, run_path)
        subprocess.call(f'cd {run_path} & citycat.exe -r 1 -c 1', shell=True)
        output.Output(os.path.join(run_path, 'R1C1_SurfaceMaps')).to_netcdf(
            os.path.join(out_path, f'{self.run_name}-{self.run_id}.nc'), attributes={
                param: value if type(value) in [float, int] else str(value)
                for param, value in self.__dict__.items() if param != 'model'}, srid=self.srid)


def fetch(con, run_id, run_table='runs'):
    query = sql.SQL("""
    SELECT 
        run_id,
        run_duration, 
        srid, 
        resolution, 
        run_name, 
        domain_table,
        dem_table,
        rain_table,
        rain_start,
        rain_end,
        output_frequency,
        rain_total,
        rain_duration,
        friction,
        green_areas_table,
        buildings_table,
        version_number
    
    FROM {run_table}
    WHERE run_id = %(run_id)s
    """).format(run_table=sql.Identifier(run_table))
    with con:
        with con.cursor() as cur:
            cur.execute(query, dict(run_id=run_id))
            response = cur.fetchone()
            assert response is not None, 'Run does not exist in database'
            (
                run_id,
                run_duration,
                srid,
                resolution,
                run_name,
                domain_table,
                dem_table,
                rain_table,
                rain_start,
                rain_end,
                output_frequency,
                rain_total,
                rain_duration,
                friction,
                green_areas_table,
                buildings_table,
                version_number
            ) = response

    return Run(
        run_id=run_id,
        run_duration=run_duration,
        srid=srid,
        resolution=resolution,
        run_name=run_name,
        domain_table=domain_table,
        dem_table=dem_table,
        rain_table=rain_table,
        rain_start=rain_start,
        rain_end=rain_end,
        output_frequency=output_frequency,
        rain_total=rain_total,
        rain_duration=rain_duration,
        friction=friction,
        green_areas_table=green_areas_table,
        buildings_table=buildings_table,
        version_number=version_number
    )
