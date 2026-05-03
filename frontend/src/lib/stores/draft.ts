import { writable } from 'svelte/store';

export interface Hero {
	id: number;
	localized_name: string;
	primary_attr: 'agi' | 'str' | 'int' | 'all';
	img: string;
	icon: string;
}

export interface DraftState {
	roomId: string;
	radiantPicks: Hero[];
	direPicks: Hero[];
	radiantBans: Hero[];
	direBans: Hero[];
	availableHeroes: Hero[];
	// CM sequence state
	phase: string;          // "Ban Phase 1" | "Pick Phase 1" | … | "Draft Complete"
	turn: string;           // "radiant" | "dire" | ""
	action: string;         // "pick" | "ban" | ""
	seqIndex: number;
	totalSteps: number;
	draftComplete: boolean;
	// Room meta
	isHost: boolean;
	roomClosed: boolean;
	roomClosedReason: string;
}

function createDraftStore() {
	const initial: DraftState = {
		roomId: '',
		radiantPicks: [],
		direPicks: [],
		radiantBans: [],
		direBans: [],
		availableHeroes: [],
		phase: '',
		turn: '',
		action: '',
		seqIndex: 0,
		totalSteps: 22,
		draftComplete: false,
		isHost: false,
		roomClosed: false,
		roomClosedReason: ''
	};

	const { subscribe, set, update } = writable<DraftState>(initial);

	function heroById(id: number, heroes: Hero[]): Hero | undefined {
		return heroes.find((h) => h.id === id);
	}

	return {
		subscribe,

		setHeroes(heroes: Hero[]) {
			update((s) => ({ ...s, availableHeroes: heroes }));
		},

		setRoomId(roomId: string) {
			update((s) => ({ ...s, roomId }));
		},

		applyRoomState(
			serverState: {
				radiant_picks: number[];
				dire_picks: number[];
				radiant_bans: number[];
				dire_bans: number[];
				phase: string;
				turn: string;
				action?: string;
				seq_index?: number;
				total_steps?: number;
				draft_complete?: boolean;
				is_host?: boolean;
			},
			allHeroes: Hero[]
		) {
			const takenIds = new Set([
				...serverState.radiant_picks,
				...serverState.dire_picks,
				...serverState.radiant_bans,
				...serverState.dire_bans
			]);

			update((s) => ({
				...s,
				radiantPicks: serverState.radiant_picks.map((id) => heroById(id, allHeroes)).filter(Boolean) as Hero[],
				direPicks: serverState.dire_picks.map((id) => heroById(id, allHeroes)).filter(Boolean) as Hero[],
				radiantBans: serverState.radiant_bans.map((id) => heroById(id, allHeroes)).filter(Boolean) as Hero[],
				direBans: serverState.dire_bans.map((id) => heroById(id, allHeroes)).filter(Boolean) as Hero[],
				availableHeroes: allHeroes.filter((h) => !takenIds.has(h.id)),
				phase: serverState.phase,
				turn: serverState.turn,
				action: serverState.action ?? s.action,
				seqIndex: serverState.seq_index ?? s.seqIndex,
				totalSteps: serverState.total_steps ?? s.totalSteps,
				draftComplete: serverState.draft_complete ?? s.draftComplete,
				isHost: serverState.is_host ?? s.isHost
			}));
		},

		applyPick(heroId: number, team: 'radiant' | 'dire', allHeroes: Hero[]) {
			update((s) => {
				const hero = heroById(heroId, allHeroes);
				if (!hero) return s;
				const available = s.availableHeroes.filter((h) => h.id !== heroId);
				if (team === 'radiant') {
					return { ...s, radiantPicks: [...s.radiantPicks, hero], availableHeroes: available };
				}
				return { ...s, direPicks: [...s.direPicks, hero], availableHeroes: available };
			});
		},

		applyBan(heroId: number, team: 'radiant' | 'dire', allHeroes: Hero[]) {
			update((s) => {
				const hero = heroById(heroId, allHeroes);
				if (!hero) return s;
				const available = s.availableHeroes.filter((h) => h.id !== heroId);
				if (team === 'radiant') {
					return { ...s, radiantBans: [...s.radiantBans, hero], availableHeroes: available };
				}
				return { ...s, direBans: [...s.direBans, hero], availableHeroes: available };
			});
		},

		/** Sync full sequence state from a hero_picked / hero_banned broadcast */
		applySequenceState(state: Record<string, unknown>) {
			update((s) => ({
				...s,
				phase: (state.phase as string) ?? s.phase,
				turn: (state.turn as string) ?? s.turn,
				action: (state.action as string) ?? s.action,
				seqIndex: (state.seq_index as number) ?? s.seqIndex,
				draftComplete: (state.draft_complete as boolean) ?? s.draftComplete,
			}));
		},

		closeRoom(reason: string) {
			update((s) => ({ ...s, roomClosed: true, roomClosedReason: reason }));
		},

		reset() {
			set(initial);
		}
	};
}

export const draftStore = createDraftStore();
