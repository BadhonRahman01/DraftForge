<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { connect, disconnect, send, onMessage, connectionStatus } from '$lib/ws';
	import { draftStore, type Hero } from '$lib/stores/draft';

	const roomId: string = $page.params.id ?? '';

	let activeTeam: 'radiant' | 'dire' = 'radiant';
	let teamAssigned = false;
	let allHeroes: Hero[] = [];
	let loading = true;
	let fetchError = '';
	let peers = 1;

	const ATTR_COLOR: Record<string, string> = {
		agi: '#33c87b',
		str: '#e05454',
		int: '#5ba7e5',
		all: '#c0a050'
	};
	const CDN = 'https://cdn.cloudflare.steamstatic.com';

	// ── Hero loading ────────────────────────────────────────────────────────

	function heroImgUrl(h: Record<string, unknown>, kind: 'img' | 'icon'): string {
		const short = (h.name as string).replace('npc_dota_hero_', '');
		const raw = (kind === 'img' ? h.img : h.icon) as string | undefined;
		if (raw && raw.startsWith('http')) return raw;
		if (raw && raw.startsWith('/')) return `${CDN}${raw}`;
		return kind === 'icon'
			? `${CDN}/apps/dota2/images/dota_react/heroes/icons/${short}.png`
			: `${CDN}/apps/dota2/images/dota_react/heroes/${short}.png`;
	}

	async function loadHeroes() {
		try {
			const res = await fetch('/api/heroes');
			if (!res.ok) throw new Error(`backend:${res.status}`);
			allHeroes = await res.json();
		} catch {
			try {
				const res2 = await fetch('https://api.opendota.com/api/heroes');
				if (!res2.ok) throw new Error(`OpenDota: HTTP ${res2.status}`);
				const raw: Array<Record<string, unknown>> = await res2.json();
				allHeroes = raw.map((h) => ({
					id: h.id as number,
					localized_name: h.localized_name as string,
					primary_attr: h.primary_attr as Hero['primary_attr'],
					img: heroImgUrl(h, 'img'),
					icon: heroImgUrl(h, 'icon'),
				}));
			} catch (e2) {
				fetchError = e2 instanceof Error ? e2.message : 'Failed to load heroes';
			}
		} finally {
			if (allHeroes.length > 0) draftStore.setHeroes(allHeroes);
			loading = false;
		}
	}

	// ── WebSocket messages ───────────────────────────────────────────────────

	function handleWsMessage(event: Record<string, unknown>) {
		const type = event.type as string;
		const data = event.data as Record<string, unknown>;

		if (type === 'room_state') {
			draftStore.applyRoomState(data as Parameters<typeof draftStore.applyRoomState>[0], allHeroes);
			peers = (data.peers as number | undefined) ?? peers;
			if (!teamAssigned) {
				activeTeam = (data.is_host as boolean) ? 'radiant' : 'dire';
				teamAssigned = true;
			}
		} else if (type === 'hero_picked' || type === 'hero_banned') {
			// Server embeds full state in every pick/ban broadcast so sequence advances for everyone
			const state = data.state as Record<string, unknown>;
			draftStore.applyRoomState(
				state as Parameters<typeof draftStore.applyRoomState>[0],
				allHeroes
			);
		} else if (type === 'presence') {
			peers = (data.peers as number) ?? peers;
		} else if (type === 'room_closed') {
			const reason = (data.message as string) || 'Room has ended';
			draftStore.closeRoom(reason);
			disconnect();
		} else if (type === 'error') {
			console.warn('[WS] Server error:', data.message);
		}
	}

	// ── Draft actions ────────────────────────────────────────────────────────

	function selectHero(hero: Hero) {
		if (draft.turn !== activeTeam || draft.draftComplete) return;
		const msgType = draft.action === 'pick' ? 'pick_hero' : 'ban_hero';
		send(msgType, { hero_id: hero.id, team: activeTeam });
	}

	function leaveRoom() {
		send('leave_room', {});
		disconnect();
		goto('/');
	}

	function endRoom() {
		send('end_room', {});
	}

	// ── Lifecycle ────────────────────────────────────────────────────────────

	onMount(async () => {
		draftStore.setRoomId(roomId);
		onMessage(handleWsMessage);
		await loadHeroes();
		const hostToken = sessionStorage.getItem(`draftforge_host_${roomId}`) ?? '';
		connect(roomId, hostToken);
	});

	onDestroy(() => {
		disconnect();
		draftStore.reset();
	});

	$: draft = $draftStore;
	$: status = $connectionStatus;
	$: myTurn = !draft.draftComplete && draft.turn === activeTeam;
	$: turnLabel = draft.draftComplete
		? 'Draft Complete'
		: myTurn
			? `Your turn — ${draft.action === 'pick' ? 'PICK' : 'BAN'} a hero`
			: `${draft.turn === 'radiant' ? '▲ Radiant' : '▼ Dire'} is ${draft.action === 'pick' ? 'picking' : 'banning'}…`;

	$: if (draft.roomClosed) {
		setTimeout(() => goto('/'), 3000);
	}
</script>

<svelte:head>
	<title>DraftForge — Room {roomId}</title>
</svelte:head>

<!-- Room closed overlay -->
{#if draft.roomClosed}
	<div class="overlay">
		<div class="overlay-card overlay-closed">
			<div class="overlay-icon">✕</div>
			<h2>Room Ended</h2>
			<p>{draft.roomClosedReason}</p>
			<p class="hint">Redirecting to home…</p>
			<a class="btn-home" href="/">Go Home Now</a>
		</div>
	</div>
{/if}

<div class="layout">
	<!-- ── Header ── -->
	<header>
		<a class="brand" href="/">DraftForge</a>
		<div class="room-info">
			<span class="room-id">Room: <code>{roomId}</code></span>
			<span class="peers">{peers} connected</span>
		</div>
		<div class="controls">
			<span class="team-badge" class:team-radiant={activeTeam === 'radiant'} class:team-dire={activeTeam === 'dire'}>
				{activeTeam === 'radiant' ? '▲ Radiant' : '▼ Dire'}
			</span>
			<span class="status-badge" class:live={status === 'open'} class:reconnecting={status !== 'open'}>
				{status === 'open' ? '● Live' : '● Reconnecting…'}
			</span>
			{#if draft.isHost}
				<button class="btn btn-end" on:click={endRoom}>End Room</button>
			{:else}
				<button class="btn btn-leave" on:click={leaveRoom}>Leave Room</button>
			{/if}
		</div>
	</header>

	<!-- ── Main draft area ── -->
	<div class="draft-area">

		<!-- Radiant panel -->
		<aside class="team-panel radiant-panel">
			<h2 class="team-title radiant-title">▲ Radiant</h2>
			<section class="slot-section">
				<h3>Picks</h3>
				<div class="slots">
					{#each Array(5) as _, i}
						{@const hero = draft.radiantPicks[i]}
						<div class="slot" class:filled={!!hero}>
							{#if hero}
								<img src={hero.img} alt={hero.localized_name} />
								<span class="slot-name">{hero.localized_name}</span>
							{:else}
								<span class="slot-empty">{i + 1}</span>
							{/if}
						</div>
					{/each}
				</div>
			</section>
			<section class="slot-section">
				<h3>Bans</h3>
				<div class="slots">
					{#each Array(6) as _, i}
						{@const hero = draft.radiantBans[i]}
						<div class="slot ban-slot" class:filled={!!hero}>
							{#if hero}
								<img src={hero.img} alt={hero.localized_name} class="banned" />
								<span class="slot-name">{hero.localized_name}</span>
							{:else}
								<span class="slot-empty">{i + 1}</span>
							{/if}
						</div>
					{/each}
				</div>
			</section>
		</aside>

		<!-- Hero grid -->
		<main class="hero-grid-area">

			<!-- Turn indicator -->
			<div class="turn-bar"
				class:turn-radiant={!draft.draftComplete && draft.turn === 'radiant'}
				class:turn-dire={!draft.draftComplete && draft.turn === 'dire'}
				class:turn-complete={draft.draftComplete}
				class:turn-mine={myTurn}
			>
				<span class="phase-label">{draft.phase || '…'}</span>
				<span class="turn-label">{turnLabel}</span>
				<span class="step-counter">
					{#if !draft.draftComplete}
						{draft.seqIndex + 1} / {draft.totalSteps}
					{:else}
						{draft.totalSteps} / {draft.totalSteps}
					{/if}
				</span>
			</div>

			<!-- Progress bar -->
			<div class="progress-track">
				<div class="progress-fill" style="width:{(draft.seqIndex / draft.totalSteps) * 100}%"></div>
			</div>

			{#if loading}
				<div class="center-msg">Loading heroes from OpenDota…</div>
			{:else if fetchError}
				<div class="center-msg error">{fetchError}</div>
			{:else if draft.draftComplete}
				<div class="center-msg complete">
					<div class="complete-icon">✓</div>
					<p>Draft complete!</p>
					<p class="hint-small">Both teams are ready.</p>
				</div>
			{:else}
				<div class="hero-grid" class:grid-inactive={!myTurn}>
					{#each draft.availableHeroes as hero (hero.id)}
						<button
							class="hero-card"
							class:hero-pick-hover={myTurn && draft.action === 'pick'}
							class:hero-ban-hover={myTurn && draft.action === 'ban'}
							disabled={!myTurn}
							title="{hero.localized_name} — {hero.primary_attr}"
							on:click={() => selectHero(hero)}
						>
							<img src={hero.img} alt={hero.localized_name} />
							<div class="hero-card-footer">
								<span class="attr-dot" style="background:{ATTR_COLOR[hero.primary_attr] ?? '#888'}"></span>
								<span class="hero-card-name">{hero.localized_name}</span>
							</div>
						</button>
					{/each}
				</div>
			{/if}
		</main>

		<!-- Dire panel -->
		<aside class="team-panel dire-panel">
			<h2 class="team-title dire-title">▼ Dire</h2>
			<section class="slot-section">
				<h3>Picks</h3>
				<div class="slots">
					{#each Array(5) as _, i}
						{@const hero = draft.direPicks[i]}
						<div class="slot" class:filled={!!hero}>
							{#if hero}
								<img src={hero.img} alt={hero.localized_name} />
								<span class="slot-name">{hero.localized_name}</span>
							{:else}
								<span class="slot-empty">{i + 1}</span>
							{/if}
						</div>
					{/each}
				</div>
			</section>
			<section class="slot-section">
				<h3>Bans</h3>
				<div class="slots">
					{#each Array(6) as _, i}
						{@const hero = draft.direBans[i]}
						<div class="slot ban-slot" class:filled={!!hero}>
							{#if hero}
								<img src={hero.img} alt={hero.localized_name} class="banned" />
								<span class="slot-name">{hero.localized_name}</span>
							{:else}
								<span class="slot-empty">{i + 1}</span>
							{/if}
						</div>
					{/each}
				</div>
			</section>
		</aside>

	</div>
</div>

<style>
	:global(body) {
		margin: 0;
		background: #0d1117;
		color: #e6edf3;
		font-family: 'Segoe UI', system-ui, sans-serif;
	}

	.layout {
		display: flex;
		flex-direction: column;
		height: 100vh;
		overflow: hidden;
	}

	/* ── Overlay (room closed / draft complete) ── */
	.overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.75);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 100;
	}

	.overlay-card {
		background: #161b22;
		border-radius: 12px;
		padding: 2.5rem 3rem;
		text-align: center;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.75rem;
		max-width: 360px;
	}

	.overlay-closed { border: 1px solid #f85149; }

	.overlay-icon {
		width: 48px;
		height: 48px;
		border-radius: 50%;
		background: #f85149;
		color: #fff;
		font-size: 1.4rem;
		font-weight: 700;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.overlay-card h2 { margin: 0; font-size: 1.4rem; color: #f0f6fc; }
	.overlay-card p  { margin: 0; color: #8b949e; font-size: 0.9rem; }
	.hint { font-size: 0.8rem !important; color: #484f58 !important; }

	.btn-home {
		margin-top: 0.5rem;
		padding: 0.6rem 1.5rem;
		background: #e84e1d;
		color: #fff;
		border-radius: 8px;
		text-decoration: none;
		font-weight: 600;
		font-size: 0.9rem;
	}
	.btn-home:hover { background: #ff6b35; }

	/* ── Header ── */
	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem 1.5rem;
		background: #161b22;
		border-bottom: 1px solid #30363d;
		flex-shrink: 0;
		gap: 1rem;
	}

	.brand {
		font-size: 1.2rem;
		font-weight: 700;
		color: #e84e1d;
		text-decoration: none;
	}
	.brand:hover { color: #ff6b3d; }

	.room-info {
		display: flex;
		align-items: center;
		gap: 1rem;
		font-size: 0.85rem;
		color: #8b949e;
	}

	code {
		background: #0d1117;
		border: 1px solid #30363d;
		border-radius: 4px;
		padding: 1px 6px;
		font-size: 0.85rem;
		color: #79c0ff;
	}

	.controls {
		display: flex;
		align-items: center;
		gap: 1rem;
		font-size: 0.85rem;
	}

	.team-badge {
		font-size: 0.8rem;
		font-weight: 700;
		padding: 0.2rem 0.7rem;
		border-radius: 999px;
		border: 1px solid;
	}
	.team-radiant { color: #3fb950; border-color: #3fb950; }
	.team-dire    { color: #f85149; border-color: #f85149; }

	.status-badge { font-size: 0.8rem; font-weight: 600; }
	.status-badge.live        { color: #3fb950; }
	.status-badge.reconnecting{ color: #f85149; }

	.btn {
		padding: 0.3rem 0.8rem;
		border: none;
		border-radius: 6px;
		font-size: 0.8rem;
		font-weight: 600;
		cursor: pointer;
	}
	.btn-end   { background: #f85149; color: #fff; }
	.btn-end:hover   { background: #ff6b6b; }
	.btn-leave { background: #30363d; color: #e6edf3; border: 1px solid #484f58; }
	.btn-leave:hover { background: #484f58; }

	/* ── Layout ── */
	.draft-area {
		display: grid;
		grid-template-columns: 210px 1fr 210px;
		flex: 1;
		overflow: hidden;
	}

	/* ── Team panels ── */
	.team-panel {
		padding: 0.75rem;
		border-right: 1px solid #21262d;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}
	.dire-panel { border-right: none; border-left: 1px solid #21262d; }

	.team-title {
		font-size: 1rem;
		font-weight: 700;
		margin: 0;
		text-align: center;
		padding-bottom: 0.4rem;
		border-bottom: 2px solid;
	}
	.radiant-title { color: #3fb950; border-color: #3fb950; }
	.dire-title    { color: #f85149; border-color: #f85149; }

	.slot-section h3 {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #8b949e;
		margin: 0 0 0.4rem;
	}

	.slots { display: flex; flex-direction: column; gap: 0.3rem; }

	.slot {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 5px;
		padding: 0.3rem 0.4rem;
		min-height: 36px;
		font-size: 0.75rem;
	}
	.slot.filled      { border-color: #3fb950; }
	.ban-slot.filled  { border-color: #f85149; }

	.slot img {
		width: 30px;
		height: 17px;
		object-fit: cover;
		border-radius: 3px;
	}
	.slot img.banned { filter: grayscale(80%) brightness(0.55); }

	.slot-name {
		font-size: 0.7rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		color: #e6edf3;
	}
	.slot-empty { color: #484f58; font-size: 0.7rem; }

	/* ── Hero grid area ── */
	.hero-grid-area {
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	/* ── Turn bar ── */
	.turn-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem 1rem;
		background: #161b22;
		border-bottom: 2px solid #21262d;
		flex-shrink: 0;
		transition: border-color 0.2s;
	}
	.turn-bar.turn-radiant { border-color: #3fb950; }
	.turn-bar.turn-dire    { border-color: #f85149; }
	.turn-bar.turn-complete{ border-color: #58a6ff; }

	.turn-bar.turn-mine {
		background: #0d2a14;
	}
	.turn-bar.turn-mine.turn-dire {
		background: #2a0d0d;
	}

	.phase-label {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: #8b949e;
		min-width: 90px;
	}

	.turn-label {
		font-size: 0.95rem;
		font-weight: 700;
		color: #e6edf3;
		text-align: center;
		flex: 1;
	}
	.turn-bar.turn-mine .turn-label { color: #fff; }

	.step-counter {
		font-size: 0.75rem;
		color: #8b949e;
		min-width: 50px;
		text-align: right;
	}

	/* ── Progress bar ── */
	.progress-track {
		height: 3px;
		background: #21262d;
		flex-shrink: 0;
	}
	.progress-fill {
		height: 100%;
		background: #58a6ff;
		transition: width 0.3s ease;
	}

	/* ── Hero grid ── */
	.hero-grid-area > .center-msg,
	.hero-grid-area > .hero-grid {
		padding: 0.75rem 1rem;
		overflow-y: auto;
		flex: 1;
	}

	.hero-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(78px, 1fr));
		gap: 5px;
		align-content: start;
	}

	.grid-inactive {
		opacity: 0.45;
	}

	.hero-card {
		background: #161b22;
		border: 1px solid #21262d;
		border-radius: 6px;
		cursor: pointer;
		padding: 0;
		overflow: hidden;
		transition: border-color 0.1s, transform 0.1s;
		display: flex;
		flex-direction: column;
	}
	.hero-card:disabled {
		cursor: default;
	}

	/* Colour the hover based on current action */
	.hero-pick-hover:not(:disabled):hover {
		border-color: #3fb950;
		transform: scale(1.05);
		z-index: 1;
	}
	.hero-ban-hover:not(:disabled):hover {
		border-color: #f85149;
		transform: scale(1.05);
		z-index: 1;
	}

	.hero-card img {
		width: 100%;
		aspect-ratio: 16/9;
		object-fit: cover;
		display: block;
	}

	.hero-card-footer {
		display: flex;
		align-items: center;
		gap: 4px;
		padding: 2px 4px 3px;
		background: #0d1117;
	}

	.attr-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.hero-card-name {
		font-size: 0.58rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		color: #c9d1d9;
	}

	/* ── Draft complete state ── */
	.center-msg {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		color: #8b949e;
		flex: 1;
	}
	.center-msg.error { color: #f85149; }
	.center-msg.complete { color: #3fb950; }

	.complete-icon {
		font-size: 3rem;
		line-height: 1;
	}

	.hint-small { font-size: 0.8rem; color: #484f58; margin: 0; }
</style>
