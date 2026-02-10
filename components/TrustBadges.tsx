interface TrustBadgesProps {
  dnsVerified: boolean
  healthOk: boolean
  uptime?: number
}

export default function TrustBadges({ dnsVerified, healthOk, uptime }: TrustBadgesProps) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className={dnsVerified ? 'badge-green' : 'badge-gray'} title={dnsVerified ? 'DNS Verified' : 'DNS Not Verified'}>
        {dnsVerified ? 'DNS' : 'No DNS'}
      </span>
      <span className={healthOk ? 'badge-green' : 'badge-red'} title={healthOk ? 'Healthy' : 'Unhealthy'}>
        {healthOk ? 'Healthy' : 'Down'}
      </span>
      {uptime !== undefined && (
        <span
          className={uptime >= 99 ? 'badge-green' : uptime >= 95 ? 'badge-yellow' : 'badge-red'}
          title={`${uptime}% uptime (30d)`}
        >
          {uptime}%
        </span>
      )}
    </div>
  )
}
