from bottle import Bottle, template
from wsgiref.simple_server import make_server, WSGIRequestHandler
import threading
import time

app = Bottle()
server_thead = None
template_base_dir = "web/managerui/"

@app.route('/')
def home():
    return "VPINFE Manager UI"

@app.route('/hello')
def hello():
    return template(template_base_dir+'test', test="testing")

class ManagerServerThread(threading.Thread):
    def __init__(self, app, host='0.0.0.0', port=8001):
        super().__init__()
        self.server = make_server(host, port, app, handler_class=WSGIRequestHandler)
        self.daemon = True  # So thread exits when main thread exits

    def run(self):
        print("Starting server Manager UI...")
        self.server.serve_forever()
        print("Server stopped.")

    def shutdown(self):
        print("Shutting down server...")
        self.server.shutdown()

def startServer():
    global server_thread
    server_thread = ManagerServerThread(app)
    server_thread.start()
    
def stopServer():
    server_thread.shutdown()
    server_thread.join()
    print("Manager UI Server Stopped.")

