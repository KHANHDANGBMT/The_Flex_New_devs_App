import React, { useEffect, useState } from 'react';
import { SecureAPI } from '../lib/secureApi';

interface RevenueData {
  property_id: string;
  total_revenue: string;
  currency: string | null;
  reservations_count: number;
}

interface RevenueSummaryProps {
  propertyId: string;
  month: number;
  year: number;
  showRaw?: boolean;
}

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({ propertyId, month, year, showRaw }) => {
  const [data, setData] = useState<RevenueData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setData(null);
    setError('');
    SecureAPI.getDashboardSummary(propertyId, { month, year }).then(response => {
      if (active) setData(response);
    }).catch(() => {
      if (active) setError('Revenue is unavailable for this selection. Please try again.');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [propertyId, month, year]);

  if (loading) return <div className="p-6" role="status">Loading revenue…</div>;
  if (error) return <div className="p-4 text-red-500 bg-red-50 rounded-lg" role="alert">{error}</div>;
  if (!data) return null;

  // The API sends a rounded decimal string. Formatting never converts money to Number.
  const [whole, fraction] = data.total_revenue.split('.');
  const displayTotal = `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction}`;
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      {showRaw && <pre className="text-xs overflow-auto mb-4">{JSON.stringify(data, null, 2)}</pre>}
      <h2 className="text-sm font-medium text-gray-500 uppercase">Monthly Revenue</h2>
      <p className="text-3xl font-bold text-gray-900 mt-1">{data.currency} {displayTotal}</p>
      <div className="grid grid-cols-2 gap-4 mt-6 pt-4 border-t border-gray-100">
        <div><p className="text-xs text-gray-500 uppercase">Property ID</p><p>{data.property_id}</p></div>
        <div><p className="text-xs text-gray-500 uppercase">Reservations</p><p>{data.reservations_count} bookings</p></div>
      </div>
    </div>
  );
};
