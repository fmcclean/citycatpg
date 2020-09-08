import pika
from .run import fetch


def run_server(con, queue='runs', host='localhost', port=5672):
    def callback(ch, method, properties, body):

        run = fetch(con, body.decode('utf8'))
        run.get_model(con)
        run.model.write('tests/test_model_from_queue')
        if queue == 'test':
            ch.close()

    connection = pika.BlockingConnection(pika.ConnectionParameters(host=host, port=port))
    channel = connection.channel()
    channel.basic_consume(queue=queue, auto_ack=True, on_message_callback=callback)
    channel.start_consuming()
