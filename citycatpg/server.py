from .run import fetch
from datetime import datetime
import functools
import pika
import threading
import psycopg2.extensions


def run_server(con: psycopg2.extensions.connection, run_path: str, out_path: str, queue: str = 'runs',
               host: str = 'localhost', port: int = 5672, close: bool = False, **params):
    """Run a Citycatpg server that listens for messages on the specified queue

    Args:
        con: Postgres connection
        run_path: Directory in which to create the model directory
        out_path: Directory in which to create the output netCDF file
        queue: Name of AQMP queue
        host: Hostname of AQMP server
        port: Port of AQMP server
        close: Whether to stop listening when the message count reaches zero
        **params: Pika connection parameters
    """

    def ack_message(ch, delivery_tag):

        message_count = ch.queue_declare(queue=queue, durable=True).method.message_count

        ch.basic_ack(delivery_tag)
        if message_count == 0 and close:
            ch.stop_consuming()

    def do_work(conn, ch, delivery_tag, body):
        run_id = body.decode('utf8')
        print(f'[{datetime.now().replace(microsecond=0)}] Fetching {run_id}')
        run = fetch(con, run_id)
        run.get_model(con)
        run.execute(run_path, out_path)
        print(f'[{datetime.now().replace(microsecond=0)}] Completed {run_id}')
        cb = functools.partial(ack_message, ch, delivery_tag)
        conn.add_callback_threadsafe(cb)

    def on_message(ch, method_frame, header_frame, body, args):
        (conn, th) = args
        delivery_tag = method_frame.delivery_tag
        t = threading.Thread(target=do_work, args=(conn, ch, delivery_tag, body))
        t.start()
        th.append(t)

    parameters = pika.ConnectionParameters(host=host, port=port, **params)
    connection = pika.BlockingConnection(parameters)

    channel = connection.channel()
    channel.queue_declare(queue=queue, durable=True)
    channel.basic_qos(prefetch_count=1)

    threads = []
    on_message_callback = functools.partial(on_message, args=(connection, threads))
    channel.basic_consume(queue, on_message_callback)

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()

    # Wait for all to complete
    for thread in threads:
        thread.join()

    connection.close()
