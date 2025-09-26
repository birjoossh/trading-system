import socketserver
import threading
import time

class IBMockTCPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        print(f"Connection established from {self.client_address}")
        while True:
            try:
                data = self.request.recv(4096)
                if not data:
                    break
                # Decode request - real IB protocol uses binary framing
                print(str(data))
                message = data.decode(errors="ignore")
                print(f"Received: {message}")

                # Simulate different API responses
                if "API client" in message or "API connection" in message:
                    self.request.sendall(b"API server connected\n")
                elif "reqMarketData" in message:
                    # Simulate market data
                    for _ in range(3):
                        tick = f"tickPrice,{time.time()},AAPL,{150.0 + _}\n".encode()
                        self.request.sendall(tick)
                        time.sleep(1)
                elif "placeOrder" in message:
                    self.request.sendall(b"orderStatus,1,Submitted\n")
                    time.sleep(2)
                    self.request.sendall(b"orderStatus,1,Filled\n")
                elif "reqAccountSummary" in message:
                    self.request.sendall(b"AccountSummary,100000,USD\n")
                else:
                    # Default mock reply
                    print("sending Mock server: Message received")
                    self.request.sendall(b"Mock server: Message received\0\n")
                    print("Done")
            except Exception as e:
                print(f"Exception: {e}")
                break
        print(f"Connection closed from {self.client_address}")

def run_mock_server(port=7498):
    server = socketserver.TCPServer(('127.0.0.1', port), IBMockTCPHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Mock IB server running on port {port}")
    return server

if __name__ == "__main__":
    run_mock_server()
    while True:
        time.sleep(5)
