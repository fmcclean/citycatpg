import shutil
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from psycopg2.extensions import connection
import uuid
from psycopg2 import sql
from citycatio import Model
from citycatio.output import to_netcdf, to_geotiff
import pandas as pd
import rasterio as rio
import geopandas as gpd
import os
import subprocess
import warnings


@dataclass
class Run:
    """Configuration used to create and run CityCAT models from postgres

    Either (rain_table, rain_start and rain_end) or (rain_total and rain_duration) must be given

    Args:
        run_duration: Number of seconds to run the model for
        run_id: Unique identifier for the run
        run_table: Postgres table where the run configuration is stored
        run_name: Name of the run
        output_frequency: Number of seconds between each output file
        domain_table: The postgres table containing the domain boundary
        domain_id: ID of the domain boundary
        dem_table: Postgres table containing the DEM
        rain_table: Postgres table containing rainfall data
        rain_start: Start date and time of the rainfall event
        rain_end: End date and time of the rainfall event
        rain_total: Total depth of rainfall during the event in millimetres
        rain_duration: Duration of rainfall event in seconds
        friction: Friction of the domain
        green_areas_table: Postgres table containing green areas polygons
        buildings_table: Postgres table containing building polygons
        metadata_table: Postgres table containing metadata
        version_number: Version of citycatpg used to create the model
        model: Citycatio Model object
    """
    run_duration: int

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
        """Insert the configuration into the run_table

        Args:
            con: Postgres connection
        """

        query = sql.SQL("""
        CREATE TABLE IF NOT EXISTS {run_table} (
            run_id uuid PRIMARY KEY,
            run_duration int, 
            run_name text, 
            domain_table text,
            domain_id int,
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
            run_name, 
            domain_table,
            domain_id,
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
            %(run_name)s, 
            %(domain_table)s,
            %(domain_id)s,
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

    def get_model(self, con: connection, open_boundaries: bool = True):
        """Create Model using data from postgres

        Args:
            con: Postgres connection
            open_boundaries: Whether to treat domain boundaries as open

        Returns:
            citycatio.Model: Citycatio Model object
        """

        assert self.rain_table is not None or self.rain_total is not None
        rainfall, rainfall_polygons = self.get_rainfall(con)

        if open_boundaries:
            open_boundaries = gpd.GeoDataFrame(geometry=self.get_domain(con).buffer(1000))
        else:
            open_boundaries = None

        if self.buildings_table is not None:
            buildings = self.get_buildings(con)
        else:
            buildings = None

        if self.green_areas_table is not None:
            green_areas = self.get_green_areas(con)
        else:
            green_areas = None

        self.model = Model(
            dem=self.get_dem(con),
            rainfall=rainfall,
            rainfall_polygons=rainfall_polygons,
            duration=self.run_duration,
            output_interval=self.output_frequency,
            open_boundaries=open_boundaries,
            buildings=buildings,
            green_areas=green_areas
        )

    def get_dem(self, con: connection):
        """Get DEM data from postgres

        Args:
            con: Postgres connection

        Returns:
            rasterio.io.MemoryFile: DEM file
        """

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

    def get_domain(self, con: connection):
        """Get domain boundary from postgres

        Args:
            con: Postgres connection

        Returns:
            geopandas.GeoDataFrame: Domain polygon
        """

        return gpd.GeoDataFrame.from_postgis(sql.SQL("""
        SELECT geom FROM {domain_table} WHERE gid={domain_id}
        """).format(
            domain_id=sql.Literal(self.domain_id),
            domain_table=sql.Identifier(self.domain_table)
        ).as_string(con), con=con)

    def get_rainfall(self, con: connection):
        """Get rainfall data from postgres

        Args:
            con: Postgres connection

        Returns:
            Tuple[pandas.DataFrame, Optional[geopandas.GeoSeries]:
            Tuple containing rainfall values and optionally geometries
        """

        if self.rain_total is not None:
            assert self.rain_duration is not None, 'Rain duration is required if rain total is given'

            rain = pd.DataFrame({
                'rainfall': [self.rain_total / self.rain_duration] * 2 + [0] * 2
            },
                index=[0, self.rain_duration, self.rain_duration + 1, self.rain_duration + 2])

            rain /= 1000  # convert from mm to m

            return rain, None

        else:
            assert self.rain_start and self.rain_end, 'Rain start and end times are required if rain total is not given'

            with con.cursor() as cur:
                cur.execute(
                    sql.SQL('select start, frequency from {metadata_table} where dataset = %(dataset)s').format(
                        metadata_table=sql.Identifier(self.metadata_table)),
                    dict(dataset=self.rain_table)
                )
                assert cur.rowcount == 1, f'Metadata missing for {self.rain_table}'
                start, frequency = cur.fetchone()

            idx_min = ((self.rain_start-start) / frequency) + 1
            idx_max = ((self.rain_end-start) / frequency) + 1

            rain = gpd.GeoDataFrame.from_postgis(sql.SQL("""
            SELECT {rain_table}.geom, series[{idx_min}:{idx_max}]
            FROM {rain_table}, {domain_table}
            WHERE ST_Intersects({rain_table}.geom, {domain_table}.geom)
            AND {domain_table}.gid={domain_id}
            """).format(
                idx_min=sql.Literal(idx_min),
                idx_max=sql.Literal(idx_max),
                rain_table=sql.Identifier(self.rain_table),
                rain_start=sql.Literal(self.rain_start),
                rain_end=sql.Literal(self.rain_end),
                domain_table=sql.Identifier(self.domain_table),
                domain_id=sql.Literal(self.domain_id)
            ).as_string(con), con)
            geom = rain.geom
            rain = rain.series.explode()
            rain = pd.DataFrame({'values': rain.values, 'index': list(range(len(rain[0]))) * len(geom),
                                'columns': rain.index}).pivot(values='values', index='index', columns='columns')
            rain = rain.astype(float) / frequency.total_seconds() / 1000
            rain.index = pd.date_range(start=self.rain_start, freq=frequency, periods=len(rain))
            rain.index = (rain.index - rain.index[0]).total_seconds().astype(int)

            return rain if type(rain) == pd.DataFrame else rain.to_frame(), geom

    def get_buildings(self, con: connection):
        """Get buildings from postgres

        Args:
            con: Postgres connection

        Returns:
            geopandas.GeoDataFrame: Buildings polygons
        """

        return gpd.GeoDataFrame.from_postgis(sql.SQL("""
        SELECT {buildings_table}.geom 
        FROM {buildings_table}, {domain_table} 
        WHERE ST_Intersects({buildings_table}.geom, {domain_table}.geom) 
        AND {domain_table}.gid={domain_id}
        """).format(
            domain_id=sql.Literal(self.domain_id),
            buildings_table=sql.Identifier(self.buildings_table),
            domain_table=sql.Identifier(self.domain_table),
        ).as_string(con), con=con)

    def get_green_areas(self, con: connection):
        """Get green areas from postgres

        Args:
            con: Postgres connection

        Returns:
            geopandas.GeoDataFrame: Buildings polygons
        """

        return gpd.GeoDataFrame.from_postgis(sql.SQL("""
        SELECT {green_areas_table}.geom 
        FROM {green_areas_table}, {domain_table} 
        WHERE ST_Intersects({green_areas_table}.geom, {domain_table}.geom) 
        AND {domain_table}.gid={domain_id}
        """).format(
            domain_id=sql.Literal(self.domain_id),
            green_areas_table=sql.Identifier(self.green_areas_table),
            domain_table=sql.Identifier(self.domain_table),
        ).as_string(con), con=con)

    def execute(self, run_path: str, out_path: str):
        """Execute model using current configuration

        Model attribute must be present

        Args:
            run_path: Directory in which to create the model directory
            out_path: Directory in which to create the output netCDF and GeoTIFF files
        """
        assert self.model is not None, 'Please generate a Model object using get_model'
        if not os.path.exists(run_path):
            os.mkdir(run_path)
        run_path = os.path.join(run_path, f'{self.run_name}-{self.run_id}')
        self.model.write(run_path)

        executable = os.getenv('CITYCAT')
        if executable is None:
            warnings.warn('CITYCAT environment variable missing')
            return
        shutil.copy(executable, run_path)
        self.run_start = datetime.now()
        subprocess.call(f'cd {run_path} & citycat.exe -r 1 -c 1', shell=True)
        self.run_end = datetime.now()

        to_netcdf(
            in_path=os.path.join(run_path, 'R1C1_SurfaceMaps'),
            out_path=os.path.join(out_path, f'{self.run_name}-{self.run_id}.nc'),
            start_time=self.rain_start if self.rain_start is not None else datetime(1, 1, 1),
            attributes={
                param: value if type(value) in [float, int] else str(value)
                for param, value in self.__dict__.items() if param != 'model'},
            srid=self.model.dem.data.open().crs.to_epsg())

        to_geotiff(os.path.join(run_path, 'R1C1_SurfaceMaps', 'R1_C1_max_depth.csv'),
                   out_path=os.path.join(out_path, f'{self.run_name}-{self.run_id}.tif'))


def fetch(con: connection, run_id: str, run_table: str = 'runs'):
    """Get a run configuration from postgres

    Args:
        con: Postgres connection
        run_id: Unique identifier for the run
        run_table: Postgres table where the run configuration is stored

    Returns:
        Run: Configuration used to create and run CityCAT models from postgres
    """
    query = sql.SQL("""
    SELECT 
        run_id,
        run_duration, 
        run_name, 
        domain_table,
        domain_id,
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
                run_name,
                domain_table,
                domain_id,
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
        run_name=run_name,
        domain_table=domain_table,
        domain_id=domain_id,
        dem_table=dem_table,
        rain_table=rain_table,
        rain_start=rain_start,
        rain_end=rain_end,
        output_frequency=output_frequency,
        rain_total=float(rain_total) if rain_total is not None else None,
        rain_duration=int(rain_duration) if rain_duration is not None else None,
        friction=float(friction),
        green_areas_table=green_areas_table,
        buildings_table=buildings_table,
        version_number=version_number
    )
