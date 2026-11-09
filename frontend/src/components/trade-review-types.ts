export type TradeGroupLegReference = {
  legId: string;
  label: string;
  status: 'linked' | 'shared' | 'unlinked' | 'missing';
};

export type GroupSelectionIntent = { groupId: string; selected: boolean };
export type LotSelectionIntent = {
  groupId: string;
  brokerLotId: string;
  selected: boolean;
};
export type GroupTextIntent = { groupId: string; value: string };
export type GroupActionIntent = { groupId: string };
export type GroupNoteIntent = { groupId: string; note: string };
export type GroupRejectIntent = { groupId: string; reason: string };
