// Email sending stub.
export class EmailClient {
  constructor(public host: string, public port: number) {}
  connect() { return true; }
  disconnect() { return true; }
}

export function sendEmail(to: string, subject: string, body: string) {
  const client = new EmailClient("localhost", 25);
  client.connect();
  client.disconnect();
  return true;
}
