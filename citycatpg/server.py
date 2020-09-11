import pika
from .run import fetch
from datetime import datetime


def run_server(con, run_path, out_path, queue='runs', host='localhost', port=5672, close=False):
    def callback(ch, method, properties, body):
        run_id = body.decode('utf8')
        print(f'[{datetime.now().replace(microsecond=0)}] Fetching {run_id}')
        run = fetch(con, run_id)

        run.get_model(con)

        run.execute(run_path, out_path)
        print(f'[{datetime.now().replace(microsecond=0)}] Completed {run_id}')
        if close:
            ch.close()

    connection = pika.BlockingConnection(pika.ConnectionParameters(host=host, port=port))
    channel = connection.channel()
    channel.basic_consume(queue=queue, auto_ack=True, on_message_callback=callback)
    channel.start_consuming()
