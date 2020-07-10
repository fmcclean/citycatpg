from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from psycopg2.extensions import connection
import uuid
from psycopg2 import sql


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
            %(run_table)s, 
            %(run_name)s, 
            %(domain_table)s,
            %(rain_start)s,
            %(rain_end)s,
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
        with con.cursor() as cur:
            cur.execute(query, self.__dict__)


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
        rain_total=rain_total,
        rain_duration=rain_duration,
        friction=friction,
        green_areas_table=green_areas_table,
        buildings_table=buildings_table,
        upload_url=upload_url,
        hostname=hostname,
        version_number=version_number
    )
