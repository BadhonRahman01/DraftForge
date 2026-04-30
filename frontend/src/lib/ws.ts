import { writable, type Readable } from 'svelte/store';

export type ConnectionStatus = 'connecting' | 'open' | 'closed';
type MessageCallback = (event: Record<string, unknown>) => void;

const BACKOFF_MS = [500, 1000, 2000, 4000, 8000, 16000];

// Exported readable store so components can react to connection state
const _status = writable<ConnectionStatus>('closed');
export const connectionStatus: Readable<ConnectionStatus> = { subscribe: _status.subscribe };

let socket: WebSocket | null = null;
let currentRoomId: string | null = null;
let retryCount = 0;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let messageHandler: MessageCallback | null = null;
let intentionalClose = false;

function getBackoff(): number {
	return BACKOFF_MS[Math.min(retryCount, BACKOFF_MS.length - 1)];
}

function scheduleReconnect(): void {
	if (intentionalClose || currentRoomId === null) return;
	const delay = getBackoff();
	console.log(`[WS] Reconnecting in ${delay}ms (attempt ${retryCount + 1})`);
	retryTimer = setTimeout(() => {
		retryCount++;
		connect(currentRoomId!);
	}, delay);
}

export function connect(roomId: string): void {
	intentionalClose = false;
	currentRoomId = roomId;

	if (socket && socket.readyState !== WebSocket.CLOSED) {
		socket.close();
	}

	const url = `ws://localhost:8000/ws/${roomId}`;
	console.log(`[WS] Connecting to ${url}`);
	_status.set('connecting');
	socket = new WebSocket(url);

	socket.onopen = () => {
		console.log(`[WS] Connected to room ${roomId}`);
		_status.set('open');
		retryCount = 0;
		if (retryTimer !== null) {
			clearTimeout(retryTimer);
			retryTimer = null;
		}
	};

	socket.onmessage = (ev: MessageEvent) => {
		try {
			const data = JSON.parse(ev.data as string) as Record<string, unknown>;
			console.log('[WS] recv', data);
			messageHandler?.(data);
		} catch (err) {
			console.error('[WS] Failed to parse message', err);
		}
	};

	socket.onerror = (err) => {
		console.error('[WS] Error', err);
	};

	socket.onclose = (ev) => {
		console.log(`[WS] Closed code=${ev.code} clean=${ev.wasClean}`);
		_status.set('closed');
		if (!intentionalClose) scheduleReconnect();
	};
}

export function disconnect(): void {
	intentionalClose = true;
	currentRoomId = null;
	if (retryTimer !== null) {
		clearTimeout(retryTimer);
		retryTimer = null;
	}
	socket?.close();
	socket = null;
	_status.set('closed');
	console.log('[WS] Disconnected intentionally');
}

export function send(type: string, payload: Record<string, unknown> = {}): void {
	if (!socket || socket.readyState !== WebSocket.OPEN) {
		console.warn('[WS] Cannot send — socket not open');
		return;
	}
	const msg = JSON.stringify({ type, payload });
	console.log('[WS] send', { type, payload });
	socket.send(msg);
}

export function onMessage(cb: MessageCallback): void {
	messageHandler = cb;
}
