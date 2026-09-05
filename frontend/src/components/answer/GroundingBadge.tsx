import React from 'react';
import { ShieldCheckIcon, ShieldAlertIcon } from 'lucide-react';
import { Badge } from '../common/Badge';

interface GroundingBadgeProps {
  verified: boolean;
  unverifiedCount: number;
}

export function GroundingBadge({ verified, unverifiedCount }: GroundingBadgeProps) {
  if (verified) {
    return (
      <Badge
        tone="neutral"
        icon={<ShieldCheckIcon aria-hidden="true" className="h-3.5 w-3.5 text-accent" />}
        title="Every crew ID, flight ID and number in this answer was checked against the evidence ledger.">
        
        All claims verified
      </Badge>);

  }

  return (
    <Badge
      tone="warning"
      icon={<ShieldAlertIcon aria-hidden="true" className="h-3.5 w-3.5" />}
      title="Some statements could not be traced back to operational data.">
      
      {unverifiedCount} claim{unverifiedCount === 1 ? '' : 's'} unverified
    </Badge>);

}