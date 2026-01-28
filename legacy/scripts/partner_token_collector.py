#!/usr/bin/env python3
"""
Simple HTTP server that listens on 127.0.0.1:5005/spotify-partner-tokens
and writes the JSON body it receives to spotify_partner_tokens.json
"""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler


class TokenHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/spotify-partner-tokens":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            
            try:
                data = json.loads(body)
                with open("spotify_partner_tokens.json", "w") as f:
                    json.dump(data, f, indent=2)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode())
                print(f"Saved tokens to spotify_partner_tokens.json")
            except json.JSONDecodeError as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 5005), TokenHandler)
    print("Listening on http://127.0.0.1:5005/spotify-partner-tokens")
    server.serve_forever()