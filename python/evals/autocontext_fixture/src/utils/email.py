"""send_email + EmailClient."""


class EmailClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

    def connect(self):
        return True

    def disconnect(self):
        return True


def send_email(to: str, subject: str, body: str, client: EmailClient = None):
    if client is None:
        client = EmailClient("localhost", 25)
    client.connect()
    # Stub — real impl would SMTP the message.
    client.disconnect()
    return True
