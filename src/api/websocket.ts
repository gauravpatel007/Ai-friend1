export type WsEventListener = (eventType: string, data: any) => void;

class WebSocketClient {
  private socket: WebSocket | null = null;
  private listeners: Set<WsEventListener> = new Set();
  private reconnectTimer: any = null;
  private isExplicitlyClosed = false;
  private pingInterval: any = null;

  connect() {
    this.isExplicitlyClosed = false;

    // Prevent duplicate connections if socket is already open or connecting
    if (
      this.socket &&
      (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    try {
      const socket = new WebSocket(wsUrl);
      this.socket = socket;

      socket.onopen = () => {
        if (this.socket !== socket) return;
        console.log('[WS] Connected to AI Desktop Friend backend');
        this.startPing();
        this.listeners.forEach((listener) => {
          try {
            listener('ws_connection_status', { status: 'connected' });
          } catch (err) {
            console.error('[WS] Error in connection listener:', err);
          }
        });
      };

      socket.onmessage = (event) => {
        if (this.socket !== socket) return;
        try {
          const payload = JSON.parse(event.data);
          const { type, data } = payload;
          this.listeners.forEach((listener) => {
            try {
              listener(type, data);
            } catch (err) {
              console.error('[WS] Error in listener callback:', err);
            }
          });
        } catch (err) {
          console.error('[WS] Failed to parse message', err);
        }
      };

      socket.onclose = () => {
        if (this.socket !== socket) return;
        this.stopPing();
        this.socket = null;
        this.listeners.forEach((listener) => {
          try {
            listener('ws_connection_status', { status: 'disconnected' });
          } catch (err) {
            console.error('[WS] Error in connection listener:', err);
          }
        });
        if (!this.isExplicitlyClosed) {
          console.log('[WS] Connection closed, reconnecting in 2s...');
          this.reconnectTimer = setTimeout(() => this.connect(), 2000);
        }
      };

      socket.onerror = (error) => {
        if (this.socket !== socket) return;
        console.error('[WS] Error:', error);
        this.listeners.forEach((listener) => {
          try {
            listener('ws_connection_status', { status: 'disconnected' });
          } catch (err) {
            console.error('[WS] Error in connection listener:', err);
          }
        });
      };
    } catch (err) {
      console.error('[WS] Connection attempt failed:', err);
      this.reconnectTimer = setTimeout(() => this.connect(), 3000);
    }
  }

  subscribe(listener: WsEventListener) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  clearListeners() {
    this.listeners.clear();
  }

  send(type: string, data: any = {}) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type, data }));
    }
  }

  private startPing() {
    this.stopPing();
    this.pingInterval = setInterval(() => {
      this.send('ping');
    }, 20000);
  }

  private stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  disconnect() {
    this.isExplicitlyClosed = true;
    this.stopPing();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket) {
      const s = this.socket;
      this.socket = null;
      try {
        s.close();
      } catch {
        // Ignored
      }
    }
  }
}

export const wsClient = new WebSocketClient();
