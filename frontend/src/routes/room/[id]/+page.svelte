<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { connect, disconnect, send, onMessage, connectionStatus } from '$lib/ws';
	import { draftStore, type Hero } from '$lib/stores/draft';

	const roomId: string = $page.params.id ?? '';

	// Which team the local user is picking for (Phase 1: toggle manually)
	let activeTeam: 'radiant' | 'dire' = 'radiant';
	let allHeroes: Hero[] = [];
	let loading = true;
	let fetchError = '';
	let peers = 1;

	// Attribute colour mapping
	const ATTR_COLOR: Record<string, string> = {
		agi: '#33c87b',
		str: '#e05454',
		int: '#5ba7e5',
		all: '#c0a050'
	};

	async function loadHeroes() {
		try {
			const res = await fetch('http://localhost:8000/api/heroes');
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			allHeroes = await res.json();
			draftStore.setHeroes(allHeroes);
		} catch (e) {
			fetchError = e instanceof Error ? e.message : 'Failed to load heroes';
		} finally {
			loading = false;
		}
	}

	function handleWsMessage(event: Record<string, unknown>) {
		const type = event.type as string;
		const data = event.data as Record<string, unknown>;

		if (type === 'room_state') {
			draftStore.applyRoomState(data as Parameters<typeof draftStore.applyRoomState>[0], allHeroes);
			peers = (data.peers as number | undefined) ?? peers;
		} else if (type === 'hero_picked') {
			draftStore.applyPick(
				data.hero_id as number,
				data.team as 'radiant' | 'dire',
				allHeroes
			);
		} else if (type === 'hero_banned') {
			draftStore.applyBan(
				data.hero_id as number,
				data.team as 'radiant' | 'dire',
				allHeroes
			);
		} else if (type === 'presence') {
			peers = (data.peers as number) ?? peers;
		} else if (type === 'error') {
			console.warn('[WS] Server error:', data.message);
		}
	}

	function pickHero(hero: Hero) {
		send('pick_hero', { hero_id: hero.id, team: activeTeam });
	}

	function banHero(hero: Hero) {
		send('ban_hero', { hero_id: hero.id, team: activeTeam });
	}

	onMount(async () => {
		draftStore.setRoomId(roomId);
		onMessage(handleWsMessage);
		await loadHeroes();
		connect(roomId);
	});

	onDestroy(() => {
		disconnect();
		draftStore.reset();
	});

	// Reactive derived values from the store
	$: draft = $draftStore;
	$: status = $connectionStatus;
</script>

<svelte:head>
	<title>DraftForge — Room {roomId}</title>
</svelte:head>

<div class="layout">
	<!-- ── Top bar ── -->
	<header>
		<div class="brand">DraftForge</div>
		<div class="room-info">
			<span class="room-id">Room: <code>{roomId}</code></span>
			<span class="peers">{peers} connected</span>
		</div>
		<div class="controls">
			<label>
				Playing as:
				<select bind:value={activeTeam}>
					<option value="radiant">Radiant</option>
					<option value="dire">Dire</option>
				</select>
			</label>
			<span class="status-badge" class:live={status === 'open'} class:reconnecting={status !== 'open'}>
				{status === 'open' ? '● Live' : '● Reconnecting...'}
			</span>
		</div>
	</header>

	<!-- ── Main draft area ── -->
	<div class="draft-area">
		<!-- Radiant panel -->
		<aside class="team-panel radiant-panel">
			<h2 class="team-title radiant-title">Radiant</h2>

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
				<div class="slots bans">
					{#each Array(7) as _, i}
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
			<div class="hero-grid-header">
				<h2>Heroes <span class="hero-count">({draft.availableHeroes.length} available)</span></h2>
				<div class="action-hint">
					Left-click = Pick &nbsp;|&nbsp; Right-click = Ban
				</div>
			</div>

			{#if loading}
				<div class="center-msg">Loading heroes from OpenDota...</div>
			{:else if fetchError}
				<div class="center-msg error">{fetchError}</div>
			{:else}
				<div class="hero-grid">
					{#each draft.availableHeroes as hero (hero.id)}
						<button
							class="hero-card"
							title="{hero.localized_name} — {hero.primary_attr}"
							on:click={() => pickHero(hero)}
							on:contextmenu|preventDefault={() => banHero(hero)}
						>
							<img src={hero.img} alt={hero.localized_name} loading="lazy" />
							<div class="hero-card-footer">
								<span
									class="attr-dot"
									style="background:{ATTR_COLOR[hero.primary_attr] ?? '#888'}"
								></span>
								<span class="hero-card-name">{hero.localized_name}</span>
							</div>
						</button>
					{/each}
				</div>
			{/if}
		</main>

		<!-- Dire panel -->
		<aside class="team-panel dire-panel">
			<h2 class="team-title dire-title">Dire</h2>

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
				<div class="slots bans">
					{#each Array(7) as _, i}
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

	/* ── Header ── */
	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.6rem 1.5rem;
		background: #161b22;
		border-bottom: 1px solid #30363d;
		flex-shrink: 0;
		gap: 1rem;
	}

	.brand {
		font-size: 1.25rem;
		font-weight: 700;
		color: #e84e1d;
	}

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
		gap: 1.25rem;
		font-size: 0.85rem;
	}

	select {
		background: #0d1117;
		border: 1px solid #30363d;
		color: #e6edf3;
		border-radius: 6px;
		padding: 0.25rem 0.5rem;
		margin-left: 0.35rem;
		font-size: 0.85rem;
	}

	.status-badge {
		font-size: 0.8rem;
		font-weight: 600;
	}

	.status-badge.live { color: #3fb950; }
	.status-badge.reconnecting { color: #f85149; }

	/* ── Draft area ── */
	.draft-area {
		display: grid;
		grid-template-columns: 220px 1fr 220px;
		flex: 1;
		overflow: hidden;
	}

	/* ── Team panels ── */
	.team-panel {
		padding: 1rem;
		border-right: 1px solid #21262d;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.dire-panel {
		border-right: none;
		border-left: 1px solid #21262d;
	}

	.team-title {
		font-size: 1.1rem;
		font-weight: 700;
		margin: 0;
		text-align: center;
		padding-bottom: 0.5rem;
		border-bottom: 2px solid;
	}

	.radiant-title { color: #3fb950; border-color: #3fb950; }
	.dire-title { color: #f85149; border-color: #f85149; }

	.slot-section h3 {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #8b949e;
		margin: 0 0 0.5rem;
	}

	.slots {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}

	.slot {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 6px;
		padding: 0.35rem 0.5rem;
		min-height: 40px;
		font-size: 0.8rem;
	}

	.slot.filled { border-color: #3fb950; }
	.ban-slot.filled { border-color: #f85149; }

	.slot img {
		width: 32px;
		height: 18px;
		object-fit: cover;
		border-radius: 3px;
	}

	.slot img.banned {
		filter: grayscale(80%) brightness(0.6);
	}

	.slot-name {
		font-size: 0.75rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		color: #e6edf3;
	}

	.slot-empty {
		color: #484f58;
		font-size: 0.75rem;
	}

	/* ── Hero grid ── */
	.hero-grid-area {
		display: flex;
		flex-direction: column;
		overflow: hidden;
		padding: 0.75rem 1rem;
	}

	.hero-grid-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.75rem;
		flex-shrink: 0;
	}

	.hero-grid-header h2 {
		margin: 0;
		font-size: 1rem;
		font-weight: 600;
	}

	.hero-count {
		color: #8b949e;
		font-weight: 400;
		font-size: 0.85rem;
	}

	.action-hint {
		font-size: 0.75rem;
		color: #8b949e;
	}

	.hero-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
		gap: 6px;
		overflow-y: auto;
		flex: 1;
	}

	.hero-card {
		background: #161b22;
		border: 1px solid #21262d;
		border-radius: 6px;
		cursor: pointer;
		padding: 0;
		overflow: hidden;
		transition: border-color 0.12s, transform 0.1s;
		display: flex;
		flex-direction: column;
	}

	.hero-card:hover {
		border-color: #58a6ff;
		transform: scale(1.04);
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
		font-size: 0.6rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		color: #c9d1d9;
	}

	.center-msg {
		text-align: center;
		color: #8b949e;
		padding: 3rem;
	}

	.center-msg.error { color: #f85149; }
</style>
