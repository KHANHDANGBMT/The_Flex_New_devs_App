import React, { useEffect, useState } from 'react';
import { RevenueSummary } from './RevenueSummary';
import { SecureAPI } from '../lib/secureApi';
import { useAuth } from '../contexts/AuthContext.new';

const TenantDashboard: React.FC = () => {
  const [properties, setProperties] = useState<Array<{ id: string; name: string }>>([]);
  const [selectedProperty, setSelectedProperty] = useState('');
  const [period, setPeriod] = useState(() => {
    const today = new Date();
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    SecureAPI.getDashboardProperties().then(items => {
      if (!active) return;
      setProperties(items);
      setSelectedProperty(items[0]?.id ?? '');
    }).catch(() => {
      if (active) setError('Failed to load properties');
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const [year, month] = period.split('-').map(Number);
  const validPeriod = year >= 1 && year <= 9998 && month >= 1 && month <= 12;
  return (
    <div className="p-4 lg:p-6 min-h-full">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-6 text-gray-900">Property Management Dashboard</h1>
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 space-y-6">
          <h2 className="text-xl font-medium">Monthly Revenue</h2>
          <p className="text-gray-600">Bookings checked in during the property's local calendar month.</p>
          {loading ? <p>Loading properties…</p> : error ? <p role="alert">{error}</p> : properties.length === 0 ? <p>No properties available.</p> : (
            <>
              <div className="flex flex-wrap gap-4">
                <label>Select property
                  <select className="block border rounded p-2" value={selectedProperty} onChange={e => setSelectedProperty(e.target.value)}>
                    {properties.map(property => <option key={property.id} value={property.id}>{property.name}</option>)}
                  </select>
                </label>
                <label>Reporting month
                  <input className="block border rounded p-2" type="month" min="0001-01" max="9998-12" value={period} onChange={e => setPeriod(e.target.value)} />
                </label>
              </div>
              {validPeriod && <RevenueSummary key={`${selectedProperty}:${period}`} propertyId={selectedProperty} month={month} year={year} />}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

const Dashboard: React.FC = () => {
  const { user } = useAuth();
  // Remount all report state when the authenticated identity changes.
  return user ? <TenantDashboard key={`${user.id}:${user.tenant_id}`} /> : null;
};

export default Dashboard;
