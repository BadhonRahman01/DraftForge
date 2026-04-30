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
	phase: string;
	turn: string;
}

function createDraftStore() {
	const initial: DraftState = {
		roomId: '',
		radiantPicks: [],
		direPicks: [],
		radiantBans: [],
		direBans: [],
		availableHeroes: [],
		phase: 'draft',
		turn: 'radiant'
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

		/** Called when the server sends the full room state (on join / reconnect) */
		applyRoomState(
			serverState: {
				radiant_picks: number[];
				dire_picks: number[];
				radiant_bans: number[];
				dire_bans: number[];
				phase: string;
				turn: string;
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
				turn: serverState.turn
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

		reset() {
			set(initial);
		}
	};
}

export const draftStore = createDraftStore();
