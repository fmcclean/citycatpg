import pika
from .run import fetch
from datetime import datetime
import threading


def run_server(con, run_path, out_path, queue='runs', host='localhost', port=5672, close=False):
    def callback(ch, method, properties, body):

        def execute():
            run_id = body.decode('utf8')
            print(f'[{datetime.now().replace(microsecond=0)}] Fetching {run_id}')
            run = fetch(con, run_id)
            run.get_model(con)
            run.execute(run_path, out_path)
            print(f'[{datetime.now().replace(microsecond=0)}] Completed {run_id}')

            def ack():
                message_count = ch.queue_declare(queue=queue).method.message_count
                ch.basic_ack(method.delivery_tag)
                if message_count == 0 and close:
                    ch.stop_consuming()

            connection.add_callback_threadsafe(ack)

        t = threading.Thread(target=execute, args=())
        t.start()

    connection = pika.BlockingConnection(pika.ConnectionParameters(host=host, port=port))
    channel = connection.channel()
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=queue, auto_ack=False, on_message_callback=callback)
    channel.start_consuming()
