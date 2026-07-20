// Mirrors knx_sim/web/schemas.py's TelegramResponse. `value` stays
// `unknown` rather than a specific type: most DPTs decode to
// boolean/number, but DPT 3.007 decodes to {direction, step_code} --
// display code narrows it at the point of use instead of here.
export interface Telegram {
  timestamp: number
  source: string
  destination: string
  destination_name: string | null
  service: 'read' | 'write' | 'response'
  dpt_id: string | null
  value: unknown
}

export interface WsTelegramMessage {
  type: 'telegram'
  data: Telegram
}

// Mirrors knx_sim/web/schemas.py's GroupObjectFlagsResponse/GroupObjectState/DeviceState.
export interface GroupObjectFlags {
  communication: boolean
  read: boolean
  write: boolean
  transmit: boolean
  update: boolean
}

export interface GroupObjectState {
  group_address: string
  name: string | null
  dpt_id: string
  value: unknown
  flags: GroupObjectFlags
}

export interface DeviceState {
  individual_address: string
  name: string | null
  room: string | null
  type: string
  group_objects: Record<string, GroupObjectState>
}

// Mirrors knx_sim/web/schemas.py's InjectRequest.
export interface InjectRequest {
  destination: string
  service?: 'read' | 'write' | 'response'
  dpt_id?: string | null
  value?: unknown
  source?: string | null
}

// Mirrors knx_sim/web/schemas.py's GroupAddressNameEntry.
export interface GroupAddressNameEntry {
  address: string
  name: string
}
