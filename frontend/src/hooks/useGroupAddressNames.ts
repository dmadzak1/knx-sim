import { useEffect, useState } from 'react'
import { fetchGroupAddressNames } from '../api'
import type { GroupAddressNameEntry } from '../types'

/** The installation's group address name registry (ETS-style, project-wide
 * naming independent of any one device) -- fetched once on mount, since
 * it's part of the static config the simulator was booted with, not
 * live state that changes while it's running. */
export function useGroupAddressNames(): GroupAddressNameEntry[] {
  const [entries, setEntries] = useState<GroupAddressNameEntry[]>([])

  useEffect(() => {
    let cancelled = false
    fetchGroupAddressNames()
      .then((result) => {
        if (!cancelled) setEntries(result)
      })
      .catch((err: unknown) => {
        console.error('Failed to load group address names', err)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return entries
}
