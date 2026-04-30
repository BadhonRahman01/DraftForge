<script lang="ts">
	import { goto } from '$app/navigation';

	let joinRoomId = '';
	let creating = false;
	let error = '';

	async function createRoom() {
		creating = true;
		error = '';
		try {
			const res = await fetch('http://localhost:8000/api/rooms', { method: 'POST' });
			if (!res.ok) throw new Error(`Server error: ${res.status}`);
			const { room_id } = await res.json();
			await goto(`/room/${room_id}`);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create room';
		} finally {
			creating = false;
		}
	}

	function joinRoom() {
		const id = joinRoomId.trim();
		if (!id) return;
		goto(`/room/${id}`);
	}
</script>

<svelte:head>
	<title>DraftForge — Dota 2 Draft Simulator</title>
</svelte:head>

<main>
	<div class="hero">
		<h1>DraftForge</h1>
		<p class="subtitle">Real-time collaborative Dota 2 draft board</p>
	</div>

	<div class="cards">
		<div class="card">
			<h2>Create Room</h2>
			<p>Start a new draft session and share the link with your team.</p>
			<button class="btn btn-primary" on:click={createRoom} disabled={creating}>
				{creating ? 'Creating...' : 'Create Room'}
			</button>
			{#if error}
				<p class="error">{error}</p>
			{/if}
		</div>

		<div class="divider">or</div>

		<div class="card">
			<h2>Join Room</h2>
			<p>Enter a room ID to join an existing draft session.</p>
			<div class="join-row">
				<input
					type="text"
					placeholder="Room ID (e.g. a3f9b1c2)"
					bind:value={joinRoomId}
					on:keydown={(e) => e.key === 'Enter' && joinRoom()}
				/>
				<button class="btn btn-secondary" on:click={joinRoom} disabled={!joinRoomId.trim()}>
					Join
				</button>
			</div>
		</div>
	</div>

	<footer>
		<p>Phase 1 &mdash; WebSocket real-time sync &middot; Phase 2: Redis Pub/Sub &middot; Phase 3: OT Notes</p>
	</footer>
</main>

<style>
	:global(body) {
		margin: 0;
		background: #0d1117;
		color: #e6edf3;
		font-family: 'Segoe UI', system-ui, sans-serif;
	}

	main {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 2rem;
		gap: 3rem;
	}

	.hero {
		text-align: center;
	}

	h1 {
		font-size: 3.5rem;
		font-weight: 700;
		margin: 0;
		background: linear-gradient(135deg, #e84e1d, #ff6b35);
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		background-clip: text;
	}

	.subtitle {
		color: #8b949e;
		font-size: 1.1rem;
		margin: 0.5rem 0 0;
	}

	.cards {
		display: flex;
		align-items: center;
		gap: 2rem;
		flex-wrap: wrap;
		justify-content: center;
	}

	.card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 12px;
		padding: 2rem;
		width: 300px;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.card h2 {
		margin: 0;
		font-size: 1.25rem;
		color: #f0f6fc;
	}

	.card p {
		margin: 0;
		color: #8b949e;
		font-size: 0.9rem;
		line-height: 1.5;
	}

	.divider {
		color: #30363d;
		font-size: 1rem;
		font-weight: 600;
	}

	.btn {
		padding: 0.65rem 1.25rem;
		border: none;
		border-radius: 8px;
		font-size: 0.95rem;
		font-weight: 600;
		cursor: pointer;
		transition: opacity 0.15s;
	}

	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-primary {
		background: #e84e1d;
		color: #fff;
	}

	.btn-primary:hover:not(:disabled) {
		background: #ff6b35;
	}

	.btn-secondary {
		background: #238636;
		color: #fff;
	}

	.btn-secondary:hover:not(:disabled) {
		background: #2ea043;
	}

	.join-row {
		display: flex;
		gap: 0.5rem;
	}

	input {
		flex: 1;
		background: #0d1117;
		border: 1px solid #30363d;
		border-radius: 6px;
		color: #e6edf3;
		padding: 0.6rem 0.75rem;
		font-size: 0.9rem;
		outline: none;
	}

	input:focus {
		border-color: #58a6ff;
	}

	.error {
		color: #f85149;
		font-size: 0.875rem;
		margin: 0;
	}

	footer {
		color: #484f58;
		font-size: 0.8rem;
		text-align: center;
	}
</style>
