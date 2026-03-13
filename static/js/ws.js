// ws.js — Native WebSocket wrapper with auto-reconnect
// Include via <script src="/static/js/ws.js"></script>

class GameSocket {
  constructor(onMessage) {
    this.onMessage = onMessage;
    this.ws = null;
    this.team = null;
    this.reconnectDelay = 1000;
    this._connect();
  }

  _connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    this.ws = new WebSocket(`${proto}://${location.host}/ws`);

    this.ws.onopen = () => {
      this.reconnectDelay = 1000;
      if (this.team) {
        this.ws.send(JSON.stringify({ action: "identify", team: this.team }));
      }
    };

    this.ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        this.onMessage(msg);
      } catch (_) {}
    };

    this.ws.onclose = () => {
      // Auto-reconnect with backoff (max 8s)
      setTimeout(() => {
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, 8000);
        this._connect();
      }, this.reconnectDelay);
    };

    this.ws.onerror = () => this.ws.close();
  }

  identify(team) {
    this.team = team;
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: "identify", team }));
    }
  }
}