// Mirrors knx_sim/web/schemas.py's TelegramResponse. `value` stays
// `unknown` rather than a specific type: most DPTs decode to
// boolean/number, but DPT 3.007 decodes to {direction, step_code} --
// display code narrows it at the point of use instead of here.
export interface Telegram {
  timestamp: number
  source: string
  destination: string
  service: 'read' | 'write' | 'response'
  dpt_id: string | null
  value: unknown
}

export interface WsTelegramMessage {
  type: 'telegram'
  data: Telegram
}
