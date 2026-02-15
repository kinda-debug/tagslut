# Apple Music proxy for Apple Music Web Source 4.0 for MP3Tag
# Version 1.0b4 © 2023-2024
# All Rights Reserved

from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import signal
import ssl
import sys
import time

try:
    # Python < 3.12
    from ssl import wrap_socket  # type: ignore
except Exception:
    # Python 3.12+
    def wrap_socket(sock, *args, **kwargs):
        server_side = kwargs.pop("server_side", False)
        do_handshake_on_connect = kwargs.pop("do_handshake_on_connect", True)
        suppress_ragged_eofs = kwargs.pop("suppress_ragged_eofs", True)
        server_hostname = kwargs.pop("server_hostname", None)

        certfile = kwargs.pop("certfile", None)
        keyfile = kwargs.pop("keyfile", '/Users/georgeskhawam/Library/Containers/app.mp3tag.Mp3tag/Data/Library/Application Support/Mp3tag/Sources/Apple Music Web Source 4/localhost.key')
        ca_certs = kwargs.pop("ca_certs", None)
        cert_reqs = kwargs.pop("cert_reqs", ssl.CERT_NONE)

        ctx = ssl.SSLContext(
            ssl.PROTOCOL_TLS_SERVER if server_side else ssl.PROTOCOL_TLS_CLIENT
        )

        if ca_certs:
            ctx.load_verify_locations(cafile=ca_certs)
        if certfile or keyfile:
            ctx.load_cert_chain(certfile=certfile, keyfile=keyfile)

        ctx.verify_mode = cert_reqs

        return ctx.wrap_socket(
            sock,
            server_side=server_side,
            do_handshake_on_connect=do_handshake_on_connect,
            suppress_ragged_eofs=suppress_ragged_eofs,
            server_hostname=server_hostname,
        )

import requests
import re

TOKEN = ""
USER = ""
URL = "https://amp-api.music.apple.com"
PORT = 8084
PID_FILE = os.path.join(os.path.dirname(__file__), "mp3tag_proxy.pid")

session = requests.Session()

if TOKEN == "":
    url = "https://beta.music.apple.com/"
    response = session.get(f"{url}").text
    match = re.search(r"/(assets/index-legacy-[^/]+\.js)", response)
    if match:
        legacy_js = match.group(1)
        response = session.get(f"{url}{legacy_js}").text
        match = re.search('(?=eyJh)(.*?)(?=")', response)
        if match:
            TOKEN = "Bearer " + match.group(1)

session.headers.update(
		{
				"User-Agent": "Mozilla/5.0 (Proxy 1.0)",
				"Accept": "application/json",
				"Authorization": TOKEN,
				"media-user-token": USER,
				"Content-Type": "application/json",
				"Connection": "keep-alive",
				"Origin": "https://music.apple.com"
		}
)

def log(msg):
	timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
	print(f"{timestamp} {msg}")

class request_handler(BaseHTTPRequestHandler):

	def do_GET(self):
		request_url = URL + self.path
		date = self.date_time_string(timestamp=None)
		print(f"{date} {request_url}")
		response = session.get(request_url)
		self.send_response(response.status_code)
		if response.status_code != 200:
			print(f" -- ERROR -- {response.status_code}")
			self.send_header('Content-type', 'application/json')
		else:
			print(f" -- OK --")
			self.send_header('Content-type', 'application/json')
		self.end_headers()
		self.wfile.write(response.content)

	def do_HEAD(self):
		print("HEAD")

	def do_POST(self):
		print("POST")

	def do_SPAM(self):
		print("SPAM")

def _signal_handler(signum, frame):
	log(f"[OFF] Received signal {signum}. Shutting down...")
	if server:
		server.shutdown()

def _write_pid():
	try:
		with open(PID_FILE, "w") as f:
			f.write(str(os.getpid()))
	except Exception as e:
		log(f"[WARN] Could not write PID file: {e}")

def _remove_pid():
	try:
		if os.path.exists(PID_FILE):
			os.remove(PID_FILE)
	except Exception as e:
		log(f"[WARN] Could not remove PID file: {e}")

def _stop_existing():
	if not os.path.exists(PID_FILE):
		print("No PID file found. Proxy may not be running.")
		return 1
	try:
		with open(PID_FILE, "r") as f:
			pid = int(f.read().strip())
	except Exception as e:
		print(f"Could not read PID file: {e}")
		return 1
	try:
		os.kill(pid, signal.SIGTERM)
		print(f"Sent SIGTERM to PID {pid}.")
		return 0
	except ProcessLookupError:
		print("Process not found. Removing stale PID file.")
		_remove_pid()
		return 0
	except Exception as e:
		print(f"Failed to stop process: {e}")
		return 1

if __name__ == "__main__":
	if len(sys.argv) > 1 and sys.argv[1] in ("--stop", "stop"):
		sys.exit(_stop_existing())

server = HTTPServer(('', PORT), request_handler)
server.socket = wrap_socket(server.socket, certfile="localhost.pem", keyfile="localhost.key", server_side=True)

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

_write_pid()
log("[ON ] Apple Music proxy starting...")
log(f"[ON ] Listening on https://localhost:{PORT}")

try:
	server.serve_forever()
except KeyboardInterrupt:
	log("[OFF] Keyboard interrupt. Shutting down...")
finally:
	server.server_close()
	_remove_pid()
	log("[OFF] Proxy stopped.")
